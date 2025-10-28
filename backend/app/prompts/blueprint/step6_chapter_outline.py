"""第6步：生成章节大纲
基于 blueprint.md 的详细字段定义
"""
from typing import Dict, Any, List, Tuple


def build_prompt(
    basic_info: Dict[str, Any],
    synopsis: str,
    world_setting: Dict[str, Any],
    characters: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    构建第6步的prompt（直接返回system和user prompt）

    Args:
        basic_info: 基础信息
        synopsis: 故事梗概
        world_setting: 世界观设定
        characters: 角色列表
        relationships: 角色关系

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 构建System Prompt
    system_prompt = """# 章节大纲生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责基于所有信息生成5-8章的章节大纲。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象：

```json
{{
  "chapter_outline": [
    {{
      "chapter_number": "number - 章节编号（1-6）",
      "title": "string - 8-15字章节标题，需体现本章核心冲突或钩子",
      "summary": "string - 200-300字极度详细的章节摘要，必须包含9个要素：场景、开场、核心事件、出场角色、冲突/爽点、情感曲线、章末钩子、主线推进、待续引导"
    }}
  ]
}}
```

## 字段详细要求

### chapter_number
- 必须是数字（1-6）
- 按顺序编号

### title
- 8-15字
- 体现本章核心冲突或钩子
- 格式建议：【场景/事件·情感基调】

### summary
必须包含9个要素：
1. **场景**：时间+地点+环境氛围
2. **开场**：本章如何开始
3. **核心事件**：完整情节（起因-经过-结果）
4. **出场角色**：角色及其行为/反应
5. **冲突/爽点**：核心矛盾或情绪高潮
6. **情感曲线**：主角的情绪变化
7. **章末钩子**：悬念设置
8. **主线推进**：如何推动主线
9. **待续引导**：如何吸引读者看下一章

## 6章结构标准

### 爽文节奏
- 第1章：主角被看不起 + 初露峥嵘
- 第2章：第一次打脸/装逼成功
- 第3章：更大的危机/敌人出现
- 第4章：主角能力提升 + 小高潮
- 第5章：反派压制 + 主角绝地反击
- 第6章：阶段性大胜 + 引出更强敌人

### 剧情节奏
- 第1章：日常状态 + 异常事件
- 第2-3章：调查/探索 + 揭示部分真相
- 第4章：第一个反转 + 主角认知颠覆
- 第5章：主角采取行动 + 意外后果
- 第6章：更大的阴谋浮现 + 留下关键疑问

## 特别约束
- 生成5-6章（不超过6章）
- 每章要有完整的情节
- 必须有明确的钩子吸引读者
- 与角色和世界观设定一致

## 输出检查清单
✅ 是否有5-6章？
✅ 每章是否有完整的9个要素？
✅ 是否有明确的爽点或冲突？
✅ 是否有吸引人的章末钩子？

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt
    user_prompt = f"""## 基础信息
{basic_info}

## 故事梗概
{synopsis}

## 世界观设定
{world_setting}

## 角色列表
{characters}

## 角色关系
{relationships}

请基于以上信息，生成符合要求的章节大纲JSON。"""

    return system_prompt, user_prompt
