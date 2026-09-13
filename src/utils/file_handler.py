"""
文件处理工具
"""
import errno
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Optional, Union
import aiofiles
from loguru import logger

from config import settings


class FileHandler:
    """文件处理器"""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id
        self.logger = logger.bind(service="file_handler")

    def get_project_dir(self, project_id: Optional[str] = None) -> Path:
        """获取项目目录"""
        pid = project_id or self.project_id
        if not pid:
            raise ValueError("project_id is required")
        return settings.projects_dir / pid

    def ensure_project_structure(self, project_id: Optional[str] = None) -> Path:
        """确保项目目录结构存在"""
        project_dir = self.get_project_dir(project_id)

        # 创建子目录
        subdirs = [
            "input",           # 输入文件
            "script",          # 剧本输出
            "storyboard",      # 分镜输出
            "characters",      # 角色设计
            "images",          # 生成的图像
            "videos",          # 生成的视频
            "audio",           # 音频文件
            "output",          # 最终输出
            "temp",            # 临时文件
        ]

        for subdir in subdirs:
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        self.logger.info(f"项目目录结构已创建: {project_dir}")
        return project_dir

    async def read_text(self, file_path: Union[str, Path]) -> str:
        """异步读取文本文件"""
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def write_text(self, file_path: Union[str, Path], content: str):
        """异步写入文本文件"""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        self.logger.debug(f"文件已写入: {path}")

    async def read_json(self, file_path: Union[str, Path]) -> dict:
        """异步读取JSON文件"""
        content = await self.read_text(file_path)
        return json.loads(content)

    async def write_json(self, file_path: Union[str, Path], data: Any, indent: int = 2):
        """异步写入JSON文件"""
        content = json.dumps(data, ensure_ascii=False, indent=indent)
        await self.write_text(file_path, content)

    def read_text_sync(self, file_path: Union[str, Path]) -> str:
        """同步读取文本文件"""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_text_sync(self, file_path: Union[str, Path], content: str):
        """同步写入文本文件"""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def read_json_sync(self, file_path: Union[str, Path]) -> dict:
        """同步读取JSON文件"""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json_sync(self, file_path: Union[str, Path], data: Any, indent: int = 2):
        """同步写入JSON文件"""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

    def copy_file(self, src: Union[str, Path], dst: Union[str, Path]):
        """复制文件（源路径使用 O_NOFOLLOW，避免跟随符号链接）"""
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC

        try:
            fd = os.open(os.fspath(src_path), flags)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)):
                raise ValueError(f"Refusing to follow symlink when copying: {src_path}") from exc
            raise

        try:
            with os.fdopen(fd, "rb") as src_file:
                fd = -1
                file_stat = os.fstat(src_file.fileno())
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ValueError(f"Source is not a regular file: {src_path}")
                with open(dst_path, "wb") as dst_file:
                    shutil.copyfileobj(src_file, dst_file)
            os.chmod(dst_path, stat.S_IMODE(file_stat.st_mode))
            os.utime(dst_path, ns=(file_stat.st_atime_ns, file_stat.st_mtime_ns))
        finally:
            if fd >= 0:
                os.close(fd)

        self.logger.debug(f"文件已复制: {src_path} -> {dst_path}")

    def move_file(self, src: Union[str, Path], dst: Union[str, Path]):
        """移动文件"""
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        self.logger.debug(f"文件已移动: {src_path} -> {dst_path}")

    def delete_file(self, file_path: Union[str, Path]):
        """删除文件"""
        path = Path(file_path)
        if path.exists():
            path.unlink()
            self.logger.debug(f"文件已删除: {path}")

    def list_files(
        self,
        directory: Union[str, Path],
        pattern: str = "*",
        recursive: bool = False
    ) -> list[Path]:
        """列出目录中的文件"""
        dir_path = Path(directory)
        if recursive:
            return list(dir_path.rglob(pattern))
        return list(dir_path.glob(pattern))

    def get_file_path(
        self,
        project_id: str,
        category: str,
        filename: str
    ) -> Path:
        """获取项目中的文件路径"""
        return self.get_project_dir(project_id) / category / filename

    # ==================== 项目特定路径 ====================

    def get_input_path(self, project_id: str, filename: str = "ip_content.txt") -> Path:
        """获取输入文件路径"""
        return self.get_file_path(project_id, "input", filename)

    def get_script_path(self, project_id: str, filename: str = "script.json") -> Path:
        """获取剧本文件路径"""
        return self.get_file_path(project_id, "script", filename)

    def get_storyboard_path(
        self,
        project_id: str,
        episode_id: int,
        scene_id: Optional[int] = None
    ) -> Path:
        """获取分镜文件路径"""
        if scene_id is not None:
            filename = f"ep{episode_id:02d}_sc{scene_id:02d}.json"
        else:
            filename = f"ep{episode_id:02d}.json"
        return self.get_file_path(project_id, "storyboard", filename)

    def get_character_path(self, project_id: str, filename: str = "characters.json") -> Path:
        """获取角色设计文件路径"""
        return self.get_file_path(project_id, "characters", filename)

    def get_image_path(
        self,
        project_id: str,
        episode_id: int,
        scene_id: int,
        shot_id: int,
        ext: str = "png"
    ) -> Path:
        """获取图像文件路径"""
        filename = f"ep{episode_id:02d}_sc{scene_id:02d}_shot{shot_id:03d}.{ext}"
        return self.get_file_path(project_id, "images", filename)

    def get_video_path(
        self,
        project_id: str,
        episode_id: int,
        scene_id: Optional[int] = None,
        shot_id: Optional[int] = None,
        ext: str = "mp4",
        suffix: str = ""
    ) -> Path:
        """获取视频文件路径"""
        if shot_id is not None and scene_id is not None:
            filename = f"ep{episode_id:02d}_sc{scene_id:02d}_shot{shot_id:03d}{suffix}.{ext}"
        elif scene_id is not None:
            filename = f"ep{episode_id:02d}_sc{scene_id:02d}{suffix}.{ext}"
        else:
            filename = f"ep{episode_id:02d}{suffix}.{ext}"
        return self.get_file_path(project_id, "videos", filename)

    def get_audio_path(
        self,
        project_id: str,
        episode_id: int,
        scene_id: Optional[int] = None,
        shot_id: Optional[int] = None,
        audio_type: str = "dialogue",
        ext: str = "mp3"
    ) -> Path:
        """获取音频文件路径"""
        if shot_id is not None and scene_id is not None:
            filename = f"ep{episode_id:02d}_sc{scene_id:02d}_shot{shot_id:03d}_{audio_type}.{ext}"
        elif scene_id is not None:
            filename = f"ep{episode_id:02d}_sc{scene_id:02d}_{audio_type}.{ext}"
        else:
            filename = f"ep{episode_id:02d}_{audio_type}.{ext}"
        return self.get_file_path(project_id, "audio", filename)

    def get_output_path(
        self,
        project_id: str,
        episode_id: int,
        suffix: str = "final",
        ext: str = "mp4"
    ) -> Path:
        """获取最终输出文件路径"""
        filename = f"ep{episode_id:02d}_{suffix}.{ext}"
        return self.get_file_path(project_id, "output", filename)
