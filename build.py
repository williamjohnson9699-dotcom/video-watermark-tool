"""Build a Windows portable distribution. Run with Python 3.12+."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent

def main():
    if os.name != 'nt':
        raise SystemExit('Build this Windows application on Windows.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--name', 'VideoWatermark', '--distpath', str(ROOT/'dist'), '--workpath', str(ROOT/'build'), '--specpath', str(ROOT/'build'), '--exclude-module', 'matplotlib', '--exclude-module', 'numpy', '--exclude-module', 'pandas', '--exclude-module', 'scipy', str(ROOT/'watermark.py')], cwd=ROOT, check=True)
    output = ROOT/'dist'/'VideoWatermark'
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), output/'ffmpeg.exe')
    for filename in ('README.md', 'USER_GUIDE.txt', 'FFMPEG-LICENSE.txt', 'watermark.py'):
        shutil.copy2(ROOT/filename, output/filename)
    shutil.make_archive(str(ROOT/'dist'/'video-watermark-v4.1-windows-x64'), 'zip', root_dir=output.parent, base_dir=output.name)
    print('Built:', output)

if __name__ == '__main__':
    main()
