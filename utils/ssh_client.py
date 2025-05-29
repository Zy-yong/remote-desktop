import socket
import time
import traceback
import logging

import paramiko
import json

from channels.generic.websocket import JsonWebsocketConsumer
from paramiko import BadHostKeyException, AuthenticationException, SSHException

from apps.common.consts import WsCode

logger = logging.getLogger('service')


class SSHClient(object):
    def __init__(
        self, hostname, port, username, password,
        **kwargs
    ):
        self.hostname = hostname
        self.ip = kwargs['ip']
        self.port = port
        self.username = username
        self.password = password
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_channel = None
        self.channel_name = None
        self.ws = kwargs.get('websocket')   # type: JsonWebsocketConsumer
        self.transport = paramiko.Transport(sock=(self.ip, int(self.port)))

    def ssh_connect(
        self, timeout=10, look_for_keys=False
    ):
        try:
            self.client.connect(
                hostname=self.ip,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=timeout,
                look_for_keys=look_for_keys
            )
            self.transport.connect(username=self.username, password=self.password)
        except (
            BadHostKeyException, AuthenticationException, SSHException,
            socket.error
        ) as e:
            logger.error(traceback.format_exc())
            if self.ws:
                self.ws.send(
                    text_data=json.dumps({'code': 0, 'message': 'connection failed...'})
                )
                self.ws.close()
            return
        # transport = self.client.get_transport()
        self.ssh_channel = self.transport.open_session()
        self.ssh_channel.set_name("{}_{}_{}".format(
            self.username, self.hostname, time.strftime("%Y%m%d%H%M%S")
        ))
        print('------------------', self.ssh_channel.get_name())
        # TODO 变更大小
        self.ssh_channel.get_pty()
        self.ssh_channel.invoke_shell()
        # 10分钟无输入就断开连接
        self.ssh_channel.settimeout(60*10)  # 10分钟

        for i in range(2):
            hello_world = self.ssh_channel.recv(1024).decode('utf-8', 'ignore')
            if self.ws:
                self.ws.send(
                    text_data=json.dumps({"code": WsCode.TEXT.value, 'message': hello_world.strip()})
                )
            self.ws.th.stdout.append([time.time() - self.ws.th.start_time, 'o', hello_world])

    # 断开websocket和关闭ssh通道
    def close(self):
        try:
            self.client.close()
        except:
            logger.error(traceback.format_exc())

    def resize_pty(self, cols, rows):
        self.ssh_channel.resize_pty(width=cols, height=rows)
