# 第三方说明

- **lunar-python 1.4.8**：MIT，作者 6tail。通过依赖安装使用，未复制其实现代码。来源 https://github.com/6tail/lunar-python 。历法回归样例参照该仓库 `test/EightCharTest.py` 的公开日期和预期四柱。
- **Pillow**：HPND（PIL Software License），通过依赖安装使用。来源 https://github.com/python-pillow/Pillow 。
- **GanzhiSans.otf**：由 Noto Sans CJK SC Regular 裁剪、重命名，SIL OFL 1.1。原字体版权保留在字体元数据中；许可见 `assets/fonts/LICENSE.txt`，来源及原始/输出 SHA-256 见 `assets/fonts/provenance.json`。Noto 来源 https://github.com/notofonts/noto-cjk 。构建使用工作区已有的同源 OFL 字体，不依赖其他插件运行。
- **传统概念**：《三命通会》《滴天髓阐微》《渊海子平》相关公版原典章节、香港天文台历法基础说明，链接见 `references/`。插件的候选筛选门槛、数据结构和现代宜忌为原创实现约定与释义，未复制现代译注。
- **AstrBot 接口**：参照官方开发文档 https://docs.astrbot.app/dev/star/plugin-new.html 与工作区 `_agent_reference`，并核对官方仓库的命令解析、消息组件、会话与 OneBot 主动发送接口。插件代码未复制其他插件实现。
