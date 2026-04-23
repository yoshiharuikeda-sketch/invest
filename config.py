"""
プロジェクト設定・パス管理
Mac / Windows 両対応
"""

import os
import platform
import glob

# =====================================================================
# Google Drive パス自動検出
# =====================================================================

def find_google_drive() -> str:
    """
    Google Drive for Desktop のローカルパスを自動検出する
    Mac / Windows 両対応
    """
    system = platform.system()

    if system == "Darwin":  # Mac
        # 方法1: CloudStorage（Google Drive for Desktop 新形式）
        cloud_storage = os.path.expanduser("~/Library/CloudStorage")
        if os.path.exists(cloud_storage):
            matches = glob.glob(os.path.join(cloud_storage, "GoogleDrive-*", "My Drive"))
            if matches:
                return matches[0]

        # 方法2: 旧形式
        old_path = os.path.expanduser("~/Google Drive/My Drive")
        if os.path.exists(old_path):
            return old_path

        old_path2 = os.path.expanduser("~/Google Drive")
        if os.path.exists(old_path2):
            return old_path2

    elif system == "Windows":
        # 方法1: 標準ドライブレター
        for drive in ["G:", "H:", "D:", "E:"]:
            path = os.path.join(drive, "My Drive")
            if os.path.exists(path):
                return path

        # 方法2: ユーザーフォルダ内
        user_gdrive = os.path.join(os.path.expanduser("~"), "Google Drive", "My Drive")
        if os.path.exists(user_gdrive):
            return user_gdrive

        # 方法3: AppData経由
        app_data = os.environ.get("LOCALAPPDATA", "")
        gdrive_path = os.path.join(app_data, "Google", "DriveFS")
        if os.path.exists(gdrive_path):
            matches = glob.glob(os.path.join(gdrive_path, "*", "root"))
            if matches:
                return matches[0]

    return None


# =====================================================================
# プロジェクトパス設定
# =====================================================================

# このファイルの場所（プロジェクトルート）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# Google Drive パス
GDRIVE_PATH = find_google_drive()

# シグナルファイルの保存先
# Google Driveが見つかればそこに、なければプロジェクトフォルダに保存
if GDRIVE_PATH:
    SIGNAL_OUTPUT_DIR = os.path.join(GDRIVE_PATH, "投資戦略")
    os.makedirs(SIGNAL_OUTPUT_DIR, exist_ok=True)
else:
    SIGNAL_OUTPUT_DIR = _THIS_DIR

# データキャッシュはローカルに保存（Driveの容量節約）
CACHE_DIR = _THIS_DIR

# ログの保存先
LOG_DIR = SIGNAL_OUTPUT_DIR


# =====================================================================
# 設定確認
# =====================================================================

def print_config():
    """現在の設定を表示"""
    print("=" * 55)
    print("  プロジェクト設定")
    print("=" * 55)
    print(f"  OS             : {platform.system()}")
    print(f"  プロジェクトDir : {_THIS_DIR}")
    if GDRIVE_PATH:
        print(f"  Google Drive   : ✅ {GDRIVE_PATH}")
        print(f"  シグナル出力先  : {SIGNAL_OUTPUT_DIR}")
    else:
        print(f"  Google Drive   : ❌ 未検出（ローカル保存）")
        print(f"  シグナル出力先  : {SIGNAL_OUTPUT_DIR}")
    print("=" * 55)


if __name__ == "__main__":
    print_config()
