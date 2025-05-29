import json
import logging
import selectors
import socket
import threading
import traceback

from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.assets.models import Asset
from apps.common.consts import WsCode
from apps.utils.guacamole_client.gm_config import (
    GUACD, guacd_hostname, guacd_port, SCREEN_CONFIG
)
from apps.utils.guacamole_client.client import GuacamoleClient

logger = logging.getLogger('service')


class Conn(object):
    def __init__(self, *args, **kwargs):
        self.stop = True
        self.poller = selectors.DefaultSelector()

    def select(self, timeout=1):
        events = self.poller.select(timeout=timeout)

        for key, event in events:
            data = key.data
            func = data[0]
            args = data[1:]
            try:
                func(*args)
            except:
                print(traceback.format_exc())

    def add_guacamole(self, ws):
        self.poller.register(
            ws.gd_client._client,
            selectors.EVENT_READ,
            [self.read_ser, ws],
        )
        self.check()

    def del_guacamole(self, ws):
        # ws连接断开, 注销轮播chan_ser
        try:
            if ws.gd_client._client:
                self.poller.unregister(ws.gd_client.client)
            else:
                raise
        except:
            for fileno, sel in self.poller._fd_to_key.copy().items():
                if fileno != sel.fileobj.fileno():
                    # gd_client._client连接已关闭, fileno改变
                    self.poller._fd_to_key.pop(fileno)

        ws.gd_client.close()

    def check(self):
        """
        检查轮播器是否有注册检测的元素, 是否启动线程
        :return:
        """
        if self.poller._fd_to_key and self.stop:
            # 开启run线程
            t = threading.Thread(target=self.run, daemon=True)
            t.start()

    def read_ser(self, ws):
        """
        读取后端RDP/VNC数据, 发给前端ws客户端
        后端资产 ==> guacd ==> gd_client - ws ==> ws_client
        """
        try:
            instruction = ws.gd_client.receive()
            if instruction:
                ws.send(text_data=instruction)  # 发送信息到WebSock终端显示
                # error message
                if instruction.startswith('5.error'):
                    ws.close()
            else:
                self.del_guacamole(ws)
                ws.close()
        except socket.timeout:
            print(traceback.format_exc())

    def run(self):
        self.stop = False
        print('启动 guacamole 线程...')
        while self.poller._fd_to_key:
            self.select()
        print('退出 guacamole 线程...')
        self.stop = True


class GuacamoleWs(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super(GuacamoleWs, self).__init__(*args, **kwargs)
        self.user = None
        self.asset = None
        self.account = None
        self.gd_client = None
        self.th = Conn()

    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            # self.accept(subprotocol='guacamole')  # Sec-WebSocket-Protocol
            self.accept()
            query_params = self.scope['query_params']  # type dict
            asset_id, account_id = int(query_params['asset_id']), int(query_params['account_id'])
            try:
                self.asset = get_object_or_404(Asset, pk=asset_id)
                self.account = self.asset.accounts.get(pk=account_id)
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

        file_log = '%s.log' % (timezone.now().strftime("%Y.%m.%d.%H.%M.%S"))
        try:
            # 连接本地 guacamole-server
            self.gd_client = GuacamoleClient(guacd_hostname, guacd_port)
            self.gd_client.handshake(
                protocol=self.asset.protocol,
                hostname=self.asset.ip,
                port=self.asset.port,
                username=self.account.username,
                password=self.account.password,
                width=query_params.get('width') or SCREEN_CONFIG['width'],
                height=query_params.get('height') or SCREEN_CONFIG['height'],
                # recording_name=file_log,  # 录像文件名
                **GUACD,
            )
            self.th.add_guacamole(self)
            # a = threading.Thread(target=self.data_polling, daemon=True)
            # a.start()

            # 加入channel组, 用于外部强制中止
            # self.channel_layer.group_add(str(self.log.id), self.channel_name)
        except:
            logger.error(traceback.format_exc())
            self.close()

    def receive(self, text_data=None, bytes_data=None):
        try:
            self.gd_client.send(text_data)
        except:
            logger.error(traceback.format_exc())
            self.close()

    def disconnect(self, code):
        self.th.del_guacamole(self)
