import json
import os
import re
import threading
import time
import logging
from socket import timeout

from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404

from apps.assets.models import Asset
from apps.common.consts import WsCode
from apps.utils.redis_tool import default_redis
from apps.utils.ssh_client import SSHClient
from apps.terminal.tasks import command_log, video_record_upload, black_command_log
from rzx_jms import settings
from rzx_jms.base import ONLINE_CONNECTION_COUNT, BLACK_COMMAND_CACHE

logger = logging.getLogger('service')


class WsThread(threading.Thread):
    def __init__(self, ws, *args, **kwargs):
        super(WsThread, self).__init__(daemon=True)
        self.ws = ws
        self._stop_event = threading.Event()
        self.start_time = time.time()
        self.stdout = []

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set() or not self.ws.ssh_channel.exit_status_ready():
            try:
                # 服务器返回的数据
                data = self.ws.ssh.ssh_channel.recv(1024)
                if data:
                    str_data = data.decode('utf-8', 'ignore')
                    if str_data.strip() + '\n' in self.ws.cmd_tmp:
                        continue
                    # 发给前端
                    tx = json.dumps({'code': WsCode.TEXT.value, 'message': str_data})
                    self.ws.send(text_data=tx)
                    # 记录服务器的输出
                    self.stdout.append([time.time() - self.start_time, 'o', str_data])
                    # 超过50次，就写文件，防止占内存太大
                    if len(self.stdout) >= 50:
                        self.ws.record(self.stdout)
                        self.stdout = []
                    if self.ws.tab_mode:    # 补全tab
                        tmp = str_data.split(' ')
                        if len(tmp) == 2 and tmp[1] == '' and tmp[0] != '':
                            self.ws.cmd_tmp = self.ws.cmd_tmp + tmp[0].encode().replace(b'\x07', b'').decode()
                        elif len(tmp) == 1 and tmp[0].encode() != b'\x07':  # \x07 蜂鸣声
                            self.ws.cmd_tmp = self.ws.cmd_tmp + tmp[0].encode().replace(b'\x07', b'').decode()
                        self.ws.tab_mode = False
                    if self.ws.history_mode:
                        self.ws.index = 0
                        if str_data.strip() != '':
                            self.ws.cmd_tmp = re.sub(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]|\x08', '', str_data)
                        self.ws.history_mode = False
                else:
                    return
            except timeout:
                self.ws.send(
                    text_data=json.dumps({"code": WsCode.ERROR.value, 'message': '连接服务器超时'})
                )
                break
        self.ws.send(
            text_data=json.dumps({"code": WsCode.ERROR.value, 'message': '由于长时间没有操作，连接已断开!'})
        )
        self.stdout.append([time.time() - self.start_time, 'o', '\n由于长时间没有操作，连接已断开!'])
        self.ws.close()


class TerminalWebsocket(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super(TerminalWebsocket, self).__init__(*args, **kwargs)
        self.user = None
        self.asset = None
        self.account = None
        self.th = WsThread(self)
        self.ssh = None
        self.cmd = []  # 一次连接的所有命令
        self.cmd_tmp = ''  # 一行命令
        self.tab_mode = False  # 使用tab命令补全时需要读取返回数据然后添加到当前输入命令后
        self.history_mode = False
        self.index = 0
        self.video_save_path = None
        self.video_fd = None
        self.conn_tag = None
        self.black_commands = set()

    def get_video_save_path(self):
        # 每个系统用户一个目录
        record_path = os.path.join(settings.jms_video_record, self.user.username)
        if not os.path.exists(record_path):
            os.makedirs(record_path, exist_ok=True)
        # 录像文件名
        record_file_name = '{}.{}.cast'.format(self.asset.ip, time.strftime('%Y%m%d%H%M%S'))
        record_file_path = os.path.join(record_path, record_file_name)
        return record_file_path

    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.accept()
            query_params = self.scope['query_params']   # type dict
            asset_id, account_id = int(query_params['asset_id']), int(query_params['account_id'])
            try:
                self.asset = get_object_or_404(Asset, pk=asset_id)
                self.account = self.asset.accounts.get(pk=account_id)
                if not self.account.is_active:
                    self.send(
                        text_data=json.dumps(
                            {
                                'code': WsCode.ERROR.value,
                                'message': 'account is invalid, connection fail... '
                            }))
                    self.close()
                conn_kwargs = {
                    "hostname": self.asset.hostname, "ip": self.asset.ip, 'port': self.asset.port,
                    "username": self.account.username, "password": self.account.password,
                    'websocket': self, 'os': self.asset.os
                }
                self.video_save_path = self.get_video_save_path()
                self.video_fd = open(self.video_save_path, 'a')
                # 先写录屏文件头
                self.record()
                self.ssh = SSHClient(**conn_kwargs)
                self.ssh.ssh_connect()
                # 每个ssh连接的标识
                self.conn_tag = self.ssh.ssh_channel.get_name()
                self.th.start()
                default_redis.incr(ONLINE_CONNECTION_COUNT)
                self.black_commands = default_redis.smembers(BLACK_COMMAND_CACHE) or set()
            except Asset.DoesNotExist:
                self.send(
                    text_data=json.dumps({'code': WsCode.ERROR.value, 'message': 'connection fail...'})
                )
                self.close()
        else:
            self.send(
                text_data=json.dumps({"code": WsCode.ERROR.value, 'message': 'connection fail...'})
            )
            self.close()

    def receive(self, text_data=None, bytes_data=None):
        """
        text_data = {"code": WsCode.xx.value, "message": "ll -a"}
        """
        if text_data:
            if isinstance(text_data, str):
                text_data = eval(text_data)
            command = text_data.get('message', '')
            maps = set(command.split(" ")) & self.black_commands
            if maps:
                black_command_log.delay(
                    list(maps), self.asset.hostname, self.account.name, self.user.name,
                    command
                )
            if not command.endswith('\n'):
                command += '\n'
            self.ssh.ssh_channel.send(command)
            self.gen_cmd(command)

    def disconnect(self, code=None):
        try:
            connect_time = int(time.time() - self.th.start_time)
            self.handle_cmd()
            self.record(self.th.stdout)

            if self.cmd_tmp:
                command_log.delay(
                    self.conn_tag, self.cmd_tmp,
                    self.asset.id, self.account.id, self.user.id, connect_time
                )
        finally:
            self.ssh.close()
            self.video_fd.close()
            self.th.stop()
            default_redis.decr(ONLINE_CONNECTION_COUNT)
            # 录屏文件上传
            video_record_upload.delay(
                self.conn_tag,
                self.video_save_path,
                self.account.id,
                self.asset.id,
                self.user.id
            )

    def gen_cmd(self, text_data):
        if text_data == '\r':
            self.index = 0
            if self.cmd_tmp.strip() != '':
                self.cmd.append(self.cmd_tmp)
                self.cmd_tmp = ''
        elif text_data.encode() == b'\x07':
            pass
        elif text_data.encode() in (b'\x03', b'\x01'):  # ctrl+c 和 ctrl+a
            self.index = 0
        elif text_data.encode() == b'\x05':  # ctrl+e
            self.index = len(self.cmd_tmp) - 2
        elif text_data.encode() == b'\x1b[D':  # ← 键
            if self.index == 0:
                self.index = len(self.cmd_tmp) - 2
            else:
                self.index -= 1
        elif text_data.encode() == b'\x1b[C':  # → 键
            self.index += 1
        elif text_data.encode() == b'\x7f':  # Backspace键
            if self.index == 0:
                self.cmd_tmp = self.cmd_tmp[:-1]
            else:
                self.cmd_tmp = self.cmd_tmp[:self.index] + self.cmd_tmp[self.index + 1:]
        else:
            if text_data == '\t' or text_data.encode() == b'\x1b':  # \x1b 点击2下esc键也可以补全
                self.tab_mode = True
            elif text_data.encode() == b'\x1b[A' or text_data.encode() == b'\x1b[B':
                self.history_mode = True
            else:
                if self.index == 0:
                    self.cmd_tmp += text_data
                else:
                    self.cmd_tmp = self.cmd_tmp[:self.index] + text_data + self.cmd_tmp[self.index:]

    def handle_cmd(self):  # 将vim或vi编辑文档时的操作去掉
        vi_index = None
        fg_index = None  # 捕捉使用ctrl+z将vim放到后台的操作
        q_index = None
        q_keys = (':wq', ':q', ':q!')
        for index, value in enumerate(self.cmd):
            if 'vi' in value:
                vi_index = index
            if any([key in value for key in q_keys]):
                q_index = index
            if '\x1a' in value:  # \x1a代表ctrl+z
                self.cmd[index] = value.split('\x1a')[1]
            if 'fg' in value:
                fg_index = index

        first_index = fg_index if fg_index else vi_index
        if vi_index:
            self.cmd = self.cmd[:first_index + 1] + self.cmd[q_index + 1:]

    def record(self, text=None):
        header = {
            "version": 2,
            "width": 220,
            "height": 100,
            "timestamp": round(self.th.start_time),
            "title": "ssh",
            "env": {
                "TERM": os.environ.get('TERM'),
                "SHELL": os.environ.get('SHELL', '/bin/bash')
            },
        }
        if not text:
            self.video_fd.write(json.dumps(header) + '\n')
        else:
            for txt in text:
                self.video_fd.write(json.dumps(txt) + '\n')

    @staticmethod
    def format_time(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)

        if h:
            return "%02dh:%02dm:%02ds" % (h, m, s)
        if m:
            return "%02dm:%02ds" % (m, s)
        else:
            return "%02ds" % s
