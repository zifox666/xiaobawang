import json
import re
import os
import sys

import jieba
from typing import List
from nonebot import logger

from .cache import cache_result
from .config import plugin_config, SRC_DIR


class TextProcessor:
    """文本处理工具类，用于文本分词"""

    def __init__(self):
        """
        初始化文本处理工具
        """
        self.chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        self.dict_path = plugin_config.jieba_words_path if plugin_config.jieba_words_path else SRC_DIR / "jieba.txt"
        self.replace_json = self._read_replace_word()

        if self.dict_path and os.path.exists(self.dict_path):
            jieba.load_userdict(self.dict_path)
            logger.info(f"已加载自定义词典: {self.dict_path}")
        else:
            logger.info("jieba未启用自定义词库")

        jieba.initialize()
        jieba.suggest_freq(('中', '大', '小'), True)

        if sys.platform.startswith('linux'):
            jieba.enable_parallel(12)

    @classmethod
    def _read_replace_word(cls) -> dict[str, str]:
        """
        读取错别字替换词典
        """
        replace_path = SRC_DIR / "replace.json"
        if os.path.exists(replace_path):
            with open(replace_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        return {}

    def _replace_word(self, word):
        """
        替换错别字
        """
        for pair in self.replace_json:
            for old_word, new_word in pair.items():
                word = word.replace(old_word, new_word)
        return word

    def _contains_chinese(self, text: str) -> bool:
        """
        判断文本是否包含中文
        """
        return bool(self.chinese_pattern.search(text))

    @cache_result(prefix="jieba_tokenize_")
    async def tokenize(self, text: str) -> List[str]:
        """
        根据文本语言类型进行分词
        """
        if not text or not text.strip():
            return []

        text = self._replace_word(text)

        if self._contains_chinese(text):
            if plugin_config.sde_default_participle == "jieba":
                return list(jieba.cut(text))
            else:
                words = re.split(r'(\d+|[a-zA-Z]+|[\u4e00-\u9fa5])', text)
                return [char for word in words for char in word.strip() if char.strip() != '']
        else:
            return text.split()

text_processor = TextProcessor()
