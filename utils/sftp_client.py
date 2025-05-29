import json
import logging
import os
import socket
import stat
import time
import traceback

import paramiko
from paramiko import BadHostKeyException, AuthenticationException, SSHException

from apps.common.consts import WsCode
from apps.utils.ws_data_format import WsDataFormat
from rzx_jms import settings

logger = logging.getLogger('service')


class SFTPClient(object):
    def __init__(
        self, hostname, port, username, password,
        **kwargs
    ):
        self.hostname = hostname
        self.port = int(port)
        self.username = username
        self.password = password
        self.ws = kwargs.get('websocket')  # type: JsonWebsocketConsumer
        self.os = kwargs.get('os')
        self.ip = kwargs['ip']

        self.sftp = None
        self.transport = None
        # 连接用户的默认文件操作目录
        self.current_path = kwargs.get('home_path') or settings.remote_file_home_path
        self.conn_tag = None

    def sftp_connect(self):
        try:
            self.transport = paramiko.Transport(sock=(self.ip, self.port))
            self.transport.connect(username=self.username, password=self.password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            # 切换到默认目录
            try:
                self.sftp.chdir(self.current_path)
            except IOError:
                self.sftp.mkdir(self.current_path)
                self.sftp.chdir(self.current_path)

            self.conn_tag = "{}_{}_{}".format(
                self.username, self.ip, time.strftime("%Y%m%d%H%M%S")
            )
        except (
            BadHostKeyException, AuthenticationException, SSHException,
            socket.error
        ) as e:
            logger.error(traceback.format_exc())
            if self.ws:
                self.ws.send(
                    text_data=json.dumps({'code': WsCode.ERROR.value, 'message': 'connection fail...'})
                )
                self.ws.close()
            self.close()
            return
        else:
            self.ws.send(
                text_data=json.dumps({'code': WsCode.SUCCESS.value, 'message': 'connection success'})
            )

    def close(self):
        self.sftp.close()

    def create_file(self, name):
        """
        make file
        :param name:
        :return:
        """
        path = os.path.join(self.current_path, name)
        self.sftp.put(
            localpath=os.path.join(os.getcwd(), 'create_file.example'),
            remotepath=path
        )
        return True

    def create_folder(self, name):
        """
        mkdir
        :param name:
        :return:
        """
        path = os.path.join(self.current_path, name)
        self.sftp.mkdir(path)
        return True

    def change_cwd(self, path=''):
        """
        更改此 SFTP 会话的“当前目录”
        :param path:
        :return:
        """
        if path:
            try:
                self.sftp.chdir(path)
                self.current_path = path
                return path
            except IOError:
                msg = {"code": 0, "message": "没有那个文件或目录"}
                self.ws.send(text_data=json.dumps(msg))
                return None

    def get_cwd(self):
        """
        返回此 SFTP 会话的“当前工作目录”
        :return:
        """
        assert self.sftp.getcwd() == self.current_path
        return self.sftp.getcwd()

    def list_dir(self, path=None):
        res = []
        if not path:
            path = self.current_path

        file_list = self.sftp.listdir_attr(path)
        for index, f in enumerate(file_list):
            if not stat.S_ISDIR(f.st_mode):
                is_dir = False
            else:
                is_dir = True
            res.append({'name': f.filename, 'is_dir': is_dir, 'id': index})
        return res

    def file_upload(
            self, write_fd, bytes_data,
    ):
        """
        :param write_fd:
        :param bytes_data:
        :return:
        """
        write_fd.write(bytes_data)

    def file_download(
            self, filename, prefetch=True
    ):
        """
        :param filename:
        :param prefetch:
        :return:
        """
        try:
            file_path = os.path.join(self.current_path, filename)
            file_stat = self.sftp.stat(file_path)
            origin_file_size = file_stat.st_size
            if stat.S_ISDIR(file_stat.st_mode):
                msg = {"code": WsCode.ERROR.value, "message": "仅支持文件下载！"}
                self.ws.send(text_data=json.dumps(msg))
                return False

            with self.sftp.open(file_path, "rb") as fr:
                if prefetch:
                    fr.prefetch(origin_file_size)
                while True:
                    data = fr.read(32768)
                    if len(data) == 0:
                        # 数据传输结束后 发一个空包 带文件大小，通知客户端下载结束，并校验文件大小
                        self.ws.send(
                            bytes_data=b''
                        )
                        break
                    else:
                        self.ws.send(
                            bytes_data=data
                        )
            return origin_file_size
        except:
            logger.error(traceback.format_exc())
            print(traceback.format_exc())
            return 0

    def change_name(self, old_filename, new_filename):
        old_path = os.path.join(self.current_path, old_filename)
        new_path = os.path.join(self.current_path, new_filename)
        try:
            self.sftp.rename(old_path, new_path)
            return True
        except IOError:
            return False

    def rm(self, is_dir, filename):
        try:
            if is_dir:
                self.sftp.rmdir(filename)
            else:
                remote_path = os.path.join(self.current_path, filename)
                self.sftp.unlink(remote_path)
            return True
        except:
            logger.error(traceback.format_exc())
            return False

