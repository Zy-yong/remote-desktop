import json
import os
import logging

from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404

from apps.assets.models import Asset
from apps.common.consts import WsCode, FileOperationCode
from apps.utils.sftp_client import SFTPClient
from apps.utils.ws_data_format import WsDataFormat
from apps.terminal.tasks import audit_file_record
from rzx_jms import settings

logger = logging.getLogger('service')


class FileManageWs(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super(FileManageWs, self).__init__(*args, **kwargs)
        self.user = None
        self.asset = None
        self.account = None
        self.paramiko_client = None
        self.remote_server_fd = None
        self.is_download = None

    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.accept()
            query_params = self.scope['query_params']   # type dict
            asset_id, account_id = int(query_params['asset_id']), int(query_params['account_id'])
            try:
                self.asset = get_object_or_404(Asset, pk=asset_id)
                self.account = self.asset.accounts.get(pk=account_id)
            except:
                self.send(
                    text_data=json.dumps({'code': WsCode.ERROR.value, 'message': 'connection fail...'})
                )
                self.close()
            conn_kwargs = {
                "hostname": self.asset.hostname, "ip": self.asset.ip, 'port': self.asset.port,
                "username": self.account.username, "password": self.account.password,
                'websocket': self, 'os': self.asset.os
            }
            self.paramiko_client = SFTPClient(**conn_kwargs)
            self.paramiko_client.sftp_connect()
        else:
            self.send(
                text_data=json.dumps({'code': WsCode.ERROR.value, 'message': 'connection fail...'})
            )
            self.close()

    def receive(self, text_data=None, bytes_data=None):
        """
        text_data = {
            "code": "FileOperationCode.xxx.value"
            "params": {
                "filename": 文件名,
                "is_dir": 文件夹
            }
        }
        bytes_data = b'{}'
        """
        msg = {"code": WsCode.SUCCESS.value, "message": "success"}
        if text_data:
            logger.info("client message: {}".format(text_data))
            if isinstance(text_data, str):
                text_data = eval(text_data)
            operation_type = int(text_data['code'])
            if operation_type == FileOperationCode.FINISH.value:
                if self.remote_server_fd:
                    logger.info('file upload finish!')
                    self.remote_server_fd.close()
                    self.remote_server_fd = None
                    audit_file_record.delay(
                        name=self.paramiko_client.conn_tag,
                        origin_path=self.paramiko_client.current_path,
                        target_path=self.target_path,
                        filename=self.filename,
                        operate_type=FileOperationCode.UPLOAD.value,
                        operator_id=self.account.id,
                        asset_id=self.asset.id,
                        user_id=self.user.id,
                        file_size=0
                    )
                    msg = {"code": WsCode.SUCCESS.value, "message": self.paramiko_client.list_dir()}
                    self.send(text_data=json.dumps(msg))
                    return
            elif operation_type == FileOperationCode.LISTDIR.value:
                res = self.paramiko_client.list_dir()
                msg = {"code": WsCode.SUCCESS.value, "message": json.dumps(res)}
                self.send(text_data=json.dumps(msg))
            elif operation_type == FileOperationCode.MKDIR.value:
                """
                {
                    "name": "新文件夹名"
                }
                """
                dir_name = text_data['params'].get('name')
                if self.paramiko_client.create_folder(dir_name):
                    res = self.paramiko_client.list_dir()
                    msg = {"code": WsCode.SUCCESS.value, "message": json.dumps(res)}
                    self.send(text_data=json.dumps(msg))
            elif operation_type == FileOperationCode.MKFILE.value:
                """
                {
                    "name": "新文件名"
                }
                """
                dir_name = text_data['params'].get('name')
                if self.paramiko_client.create_file(dir_name):
                    res = self.paramiko_client.list_dir()
                    msg = {"code": WsCode.SUCCESS.value, "message": json.dumps(res)}
                    self.send(text_data=json.dumps(msg))
            elif operation_type == FileOperationCode.RENAME.value:
                """
                {
                    "old_name": "原文件名",
                    "new_name": "新文件名"
                }
                """
                old_name = text_data['params'].get('old_name')
                new_name = text_data['params'].get('new_name')
                if not all([old_name, new_name]):
                    msg = {"code": WsCode.ERROR.value, "message": "参数不正确！"}
                    self.send(text_data=json.dumps(msg))
                    return
                else:
                    res = self.paramiko_client.change_name(old_name, new_name)
                    if not res:
                        msg = {"code": WsCode.ERROR.value, "message": "重命名失败！"}
                        self.send(text_data=json.dumps(msg))
                    else:
                        res = self.paramiko_client.list_dir()
                        msg = {"code": WsCode.SUCCESS.value, "message": json.dumps(res)}
                        self.send(text_data=json.dumps(msg))
                        audit_file_record.delay(
                            name=self.paramiko_client.conn_tag,
                            origin_path=self.paramiko_client.current_path,
                            target_path="",
                            filename=new_name,
                            operate_type=FileOperationCode.RENAME.value,
                            operator_id=self.account.id,
                            asset_id=self.asset.id,
                            user_id=self.user.id,
                            file_size=0
                        )

            elif operation_type == FileOperationCode.DELETE.value:
                """
                {
                    "filename": "要删除的文件",
                    "is_dir": "是否是文件夹"
                }
                """
                filename = text_data['params'].get('filename')
                is_dir = False if text_data['params'].get('is_dir') == 'false' else True
                if not self.paramiko_client.rm(is_dir, filename):
                    msg = {"code": WsCode.ERROR.value, "message": "fail"}
                    self.send(text_data=json.dumps(msg))
                else:
                    res = self.paramiko_client.list_dir()
                    msg = {"code": WsCode.SUCCESS.value, "message": json.dumps(res)}
                    self.send(text_data=json.dumps(msg))
                    audit_file_record.delay(
                        name=self.paramiko_client.conn_tag,
                        origin_path=self.paramiko_client.current_path,
                        target_path="",
                        filename=filename,
                        operate_type=FileOperationCode.DELETE.value,
                        operator_id=self.account.id,
                        asset_id=self.asset.id,
                        user_id=self.user.id,
                        file_size=0
                    )

            elif operation_type == FileOperationCode.CWD.value:
                """
                {
                    "dir_name": "目标文件夹"
                }
                """
                # 不提供文件夹名称，默认为返回上一级
                dir_name = text_data['params'].get('dir_name')
                if dir_name:
                    target_path = os.path.join(
                        self.paramiko_client.current_path,
                        dir_name
                    )
                else:
                    if self.paramiko_client.current_path in [
                        settings.remote_file_home_path
                    ]:  # 文件操作路径范围写死
                        target_path = self.paramiko_client.current_path
                    else:
                        target_path = os.path.abspath(
                            os.path.join(self.paramiko_client.current_path, '..')
                        )
                logger.info('current path: {}, change to: {}: '.format(
                    self.paramiko_client.current_path, target_path
                ))
                resp = self.paramiko_client.change_cwd(target_path)
                if resp:
                    msg = {"code": WsCode.SUCCESS.value, "message": self.paramiko_client.list_dir()}
                    self.send(text_data=json.dumps(msg))

            elif operation_type == FileOperationCode.UPLOAD.value:
                """
                    params = {
                        "filename": "文件名"
                        "origin_path": "原路径"
                    }
                    文件上传完成之后再让客户端发一个空包，不含data数据
                """
                origin_path = text_data['params'].get('origin_path')
                filename = text_data['params'].get('filename')
                file_path = os.path.join(self.paramiko_client.current_path, filename)
                if not self.remote_server_fd:
                    if not all([origin_path, filename]):
                        msg = {"code": WsCode.ERROR.value, "message": "上传文件参数不正确"}
                        self.send(
                            text_data=json.dumps(msg)
                        )
                        return
                    try:
                        remote_file_list = self.paramiko_client.list_dir(path=file_path)
                        if filename in remote_file_list:
                            msg = {"code": WsCode.ERROR.value, "message": "已存在同名文件"}
                            self.send(
                                text_data=json.dumps(msg)
                            )
                            return
                    except (IOError, FileNotFoundError):
                        print('success')
                        pass
                    self.remote_server_fd = self.paramiko_client.sftp.file(file_path, 'ab')
                self.is_download = False
                self.target_path = origin_path
                self.filename = filename
                msg = {"code": WsCode.SUCCESS.value, "message": "success"}
                self.send(
                    text_data=json.dumps(msg)
                )

            elif operation_type == FileOperationCode.DOWNLOAD.value:
                """
                    params = {
                        "filename": "文件名"
                    }
                    文件读取完成之后再给客户端发一个空包，不含data数据、标识文件下载结束
                """
                filename = text_data['params'].get('filename')
                file_size = self.paramiko_client.file_download(filename)
                if not file_size:
                    msg = {"code": WsCode.ERROR.value, "message": '下载失败'}
                    self.send(text_data=json.dumps(msg))
                    return
                else:
                    audit_file_record.delay(
                        name=self.paramiko_client.conn_tag,
                        origin_path=self.paramiko_client.current_path,
                        target_path="",
                        filename=filename,
                        operate_type=FileOperationCode.DOWNLOAD.value,
                        operator_id=self.account.id,
                        asset_id=self.asset.id,
                        user_id=self.user.id,
                        file_size=file_size
                    )
            else:
                msg = {"code": WsCode.ERROR.value, "message": "暂不支持的文件操作！"}
                self.send(text_data=json.dumps(msg))
                return
        elif bytes_data:
            # 文件上传、下载
            if not self.remote_server_fd:
                msg = {"code": WsCode.ERROR.value, "message": "数据解析失败！"}
                self.send(text_data=json.dumps(msg))
                return
            if self.is_download is True:
                pass
            elif self.is_download is False:
                self.paramiko_client.file_upload(self.remote_server_fd, bytes_data)

            # try:
            #     code, header, data = WsDataFormat.unpack(bytes_data)
            # except:
            #     msg = {"code": WsCode.ERROR.value, "message": "数据解析失败！"}
            #     self.send(text_data=json.dumps(msg))
            #     return
            # if code == FileOperationCode.UPLOAD.value:
            #     """
            #     header = {
            #         "filename": "文件名",
            #         "size": "文件大小",
            #         "origin_path": "源文件地址"
            #     }
            #     文件上传完成之后再让客户端发一个空包，不含data数据
            #     """
            #     file_size = header.get('size')
            #     origin_path = header.get('origin_path')
            #     filename = header.get('filename')
            #     file_path = os.path.join(self.paramiko_client.current_path, filename)
            #     if not self.remote_server_fd:
            #         if not all([origin_path, filename, file_size]):
            #             msg = {"message": "上传文件参数不正确"}
            #             self.send(
            #                 bytes_data=WsDataFormat.pack(WsCode.ERROR.value, msg)
            #             )
            #             return
            #         remote_file_list = self.paramiko_client.list_dir(path=file_path)
            #         if filename in remote_file_list:
            #             msg = {"message": "已存在同名文件"}
            #             self.send(
            #                 bytes_data=WsDataFormat.pack(WsCode.ERROR.value, msg)
            #             )
            #             return
            #         self.remote_server_fd = self.paramiko_client.sftp.file(file_path, 'ab')
            #     if not data:
            #         self.remote_server_fd.close()
            #         self.remote_server_fd = None
            #         s = self.paramiko_client.sftp.stat(file_path)
            #         if s.st_size != file_size:
            #             msg = {"message": "文件上传失败！"}
            #             self.send(
            #                 bytes_data=WsDataFormat.pack(WsCode.ERROR.value, msg)
            #             )
            #             self.paramiko_client.rm(False, filename)
            #             return
            #         else:
            #             audit_file_record.delay(
            #                 name=self.paramiko_client.conn_tag,
            #                 origin_path=self.paramiko_client.current_path,
            #                 target_path=origin_path,
            #                 filename=filename,
            #                 operate_type=FileOperationCode.UPLOAD.value,
            #                 operator_id=self.account.id,
            #                 asset_id=self.asset.id,
            #                 user_id=self.user.id,
            #                 file_size=file_size
            #             )
            #             msg = {"message": "文件上传成功！"}
            #             self.send(
            #                 bytes_data=WsDataFormat.pack(WsCode.SUCCESS.value, msg)
            #             )
            #             return
            #     else:
            #         self.paramiko_client.sftp.file_upload()
            #
            # elif code == FileOperationCode.DOWNLOAD.value:
            #     """
            #     header = {
            #         "filename": "文件名"
            #     }
            #     文件读取完成之后再给客户端发一个空包，不含data数据、标识文件下载结束
            #     """
            #     filename = header.get('filename')
            #     file_size = self.paramiko_client.file_download(filename)
            #     if not file_size:
            #         self.send(
            #             bytes_data=WsDataFormat.pack(WsCode.ERROR.value, '下载失败！')
            #         )
            #         return
            #     else:
            #         audit_file_record.delay(
            #             name=self.paramiko_client.conn_tag,
            #             origin_path=self.paramiko_client.current_path,
            #             target_path="",
            #             filename=filename,
            #             operate_type=FileOperationCode.DOWNLOAD.value,
            #             operator_id=self.account.id,
            #             asset_id=self.asset.id,
            #             user_id=self.user.id,
            #             file_size=file_size
            #         )
            # else:
            #     msg = {"message": "暂不支持的文件操作！"}
            #     self.send(
            #         bytes_data=WsDataFormat.pack(WsCode.ERROR.value, msg)
            #     )
            #     return

    def disconnect(self, code):
        if self.remote_server_fd:
            self.remote_server_fd.close()
