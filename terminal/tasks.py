import os
import traceback
import logging
from datetime import datetime
from urllib.parse import urljoin

from celery import shared_task

from apps.assets.models import BlackCommand
from apps.audits.serializers.command_log import CommandLogSerializer, BlackCommandLogSerializer
from apps.audits.serializers.file_serializer import VideoPlaybackSerializer, FileOperateSerializer
from apps.utils.minio_tool import minio_manager
from rzx_jms import settings


logger = logging.getLogger('service')


@shared_task
def video_record_upload(name, path, account_id, asset_id, user_id):
    """
    录屏文件保存到存储库 并记录地址
    :param name:
    :param path:
    :param account_id:
    :param asset_id:
    :param user_id:
    :return:
    """
    try:
        if os.path.exists(path):
            filename = "{}-{}".format('video-playback', path.split("/")[-1])
            res = minio_manager.file_upload(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=filename,
                file_path=path
            )
            remote_url = urljoin(
                settings.MINIO_FILE_URL_PREFIX,
                "{}/{}".format(settings.MINIO_BUCKET_NAME, res.object_name)
            )
            record = {
                'name': name,
                'filename': filename,
                'video_path': remote_url,
                'date_joined': datetime.now(),
                'account_id': account_id,
                'asset_id': asset_id,
                'user_id': user_id,

            }
            serializer = VideoPlaybackSerializer(data=record)
            if serializer.is_valid(raise_exception=False):
                serializer.save()
                os.remove(path)
            else:
                logger.error(str(serializer.errors))
    except:
        logger.error(traceback.format_exc())


@shared_task
def audit_file_record(
    name, origin_path, target_path, filename, operate_type,
    operator_id, asset_id, user_id, file_size=0
):
    try:
        serializer = FileOperateSerializer(data={
            "name": name,
            "origin_path": origin_path,
            "target_path": target_path,
            "filename": filename,
            "operate_type": operate_type,
            "operator_id": operator_id,
            "asset_id": asset_id,
            "user_id": user_id,
            "file_size": file_size,
        })
        if serializer.is_valid(raise_exception=True):
            serializer.save()
    except:
        logger.error(traceback.format_exc())


@shared_task
def command_log(name, command_str, asset_id, account_id, user_id, duration):
    """
    终端命令记录
    :param name:
    :param command_str:
    :param asset_id:
    :param account_id:
    :param user_id:
    :param duration:
    :return:
    """
    record_data = {
        "name": name,
        "command": {'command': command_str},
        "date_joined": datetime.now(),
        "executor_id": account_id,
        "asset_id": asset_id,
        "jms_user_id": user_id,
        "duration": duration,
    }
    try:
        serializer = CommandLogSerializer(data=record_data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
    except:
        logger.error(traceback.format_exc())


@shared_task
def black_command_log(commands, asset_hostname, account_name, username, command):
    """
    高危命令记录
    :param commands: 命中的高危命令集合
    :param asset_hostname:
    :param account_name:
    :param username:
    :param command: 用户输入的命令
    :return:
    """
    command_objs = BlackCommand.objects.filter(key__in=list(commands))
    for c in command_objs:
        record_data = {
            "command_id": c and c.id or None,
            "raw_command": command,
            "date_joined": datetime.now(),
            "account_name": account_name,
            "asset_hostname": asset_hostname,
            "user_name": username,
        }
        print(record_data)
        try:
            serializer = BlackCommandLogSerializer(data=record_data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
        except:
            logger.error(traceback.format_exc())
