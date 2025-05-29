"""
https://guacamole.apache.org/doc/gug/configuring-guacamole.html#connection-configuration
"""

guacd_hostname = '127.0.0.1'
guacd_port = '4822'
# guacd_ssl = 'true'  # 默认不加密, 客户端启用加密时, 需guacd本身也支持
REPLAY_PATH = '/data/jms/videos'  # 用于前端网页访问, 存放RDP/VNC录像文件夹，MEDIA_ROOT/REPLAY_PATH

# 屏幕
SCREEN_CONFIG = {
    'width': 800,
    'height': 600,
    # 'dpi': 96,  # 分辨率(DPI)
    # 'color_depth': '16',  # 色彩深度 8 16 24 32位色
    # 'resize-method': 'display-update',  # 缩放方法, display-update / reconnect, 未设置则窗口变化时不处理
    # 'read-only': 'true'
}


GUACD = {
    # TODO - need replace to _ !!
    # 如果设置为“true”，服务器返回的证书将被忽略，即使该证书无法验证。
    # 如果您普遍信任服务器以及与服务器的连接，并且您知道服务器的证书无法验证（例如，如果它是自签名的）
    'ignore_cert': 'true',

    # 用于 RDP 连接的安全模式。此模式规定如何加密数据以及将执行什么类型的身份验证（如果有）。
    # 默认情况下，根据协商过程选择安全模式，该过程确定客户端和服务器都支持什么。
    'security': 'any',

    # 如果设置为“true”，将禁用身份验证。请注意，这是指连接时进行的身份验证。
    # 服务器通过远程桌面会话强制执行的任何身份验证（例如登录对话框）仍将发生。
    # 默认情况下，身份验证处于启用状态，并且仅在服务器请求时使用
    'disable_auth': "true",

    # # 设备重定向
    # 'disable_audio': 'true',  # 禁用音频
    # 'enable_audio_input': 'true',  # 启用麦克风
    # 'enable_printing': 'true',  # 启用打印
    # 'printer_name': 'dx printer',  # 打印机设备的名称
    # 'static_channels': 'aa,bb,cc',  # 静态通道, 音频声道?

    # 'enable-drive': 'true',  # 启用虚拟盘 GUAC FS
    # 'drive_path': os.path.join(base_path, 'guacfs'),  # guacd 4822服务器路径
    # drive_path所在上级目录不存在时, 无法下载文件, 也不支持自动创建.
    # 'create_drive_path': 'true',  # guacd 服务器drive_path目录不存在则自动创建(只支持创建最后一级目录)
    # 'drive_name': 'tsclient',
    # 'disable_download': 'true',
    # 'disable_upload': 'true',

    # # 剪切板
    # 'disable_copy': 'true',  # 禁止RDP中复制
    # 'disable_paste': 'true',

    # # 屏幕录像
    # 'recording_name': '',
    'recording-path': REPLAY_PATH,  # 录像保存位置, guacd 4822服务器路径
    'create-recording-path': 'true',  # (只支持创建最后一级目录)
    # 'recording_exclude_output': 'true',  # 排除图像/数据流
    # 'recording_exclude_mouse': 'true',  # 排除鼠标
    # 'recording_include_keys': 'true',  # 包含按键事件

    # 性能
    'enable-wallpaper': 'true',  # 墙纸
    # 'enable_theming': 'true',  # 主题
    # 'enable_font_smoothing': 'true',  # 字体平滑
    # 'enable_full_window_drag': 'true',  # 全窗口拖拽 (拖动窗口显示内容)
    # 'enable_desktop_composition': 'true',  # 桌面合成效果(Aero) (透明窗口和阴影)
    # 'enable_menu_animations': 'true',  # 菜单动画
    # 'disable_bitmap_caching': 'true',  # 禁用位图缓存
    # 'disable_offscreen_caching': 'true',  # 禁用离屏缓存
    # 'disable_glyph_caching': 'true',  # 禁用字形缓存

    # 会话设置
    # 'console': 'true',  # windows控制台 id: 0
    # 'console_audio': 'true',  # 远程服务器物理位置的音频/功放

}

