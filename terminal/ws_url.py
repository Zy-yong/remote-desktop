from django.urls import path

from apps.terminal.guacamole import GuacamoleWs
from apps.terminal.ssh_websocket import TerminalWebsocket
from apps.terminal.sftp_websocket import FileManageWs

urlpatterns = [
    path('ws/terminal/', TerminalWebsocket.as_asgi(), name='terminal-ws'),
    path('ws/file/', FileManageWs.as_asgi(), name='terminal-ws-file'),
    path('ws/guacd/', GuacamoleWs.as_asgi(), name='guacd'),
]
