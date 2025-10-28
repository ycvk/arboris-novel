"""
第3步：生成世界观设定
生成 world_setting (core_rules, key_locations, factions)
基于 blueprint.md 的详细字段定义
"""

from typing import Dict, Any, Tuple


def build_prompt(basic_info: Dict[str, Any], synopsis: str) -> Tuple[str, str]:
    """
    构建第3步的prompt（直接返回system和user prompt）

    Args:
        basic_info: 基础信息
        synopsis: 故事梗概

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 构建System Prompt
    system_prompt = """# 世界观设定生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责基于基础信息和故事梗概，生成详细的世界观设定。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象，**不包含任何其他文本**：

```json
{{
  "world_setting": {{
    "core_rules": [
      {{
        "rule_content": "string - 规则的具体内容",
        "impact_on_protagonist": "string - 对主角的影响",
        "conflict_potential": "string - 潜在冲突点"
      }}
    ],
    "key_locations": [
      {{
        "name": "string - 地点名称",
        "visual_description": "string - 2-3个核心视觉元素",
        "functional_role": "string - 功能定位",
        "emotional_tone": "string - 情感基调",
        "plot_usage": "string - 剧情作用"
      }}
    ],
    "factions": [
      {{
        "name": "string - 势力名称",
        "core_interest": "string - 核心利益",
        "power_level": "string - 实力层级",
        "representative": "string - 代表人物",
        "relation_to_protagonist": "string - 与主角关系变化"
      }}
    ]
  }}
}}
```

**重要**：core_rules必须包含3个对象，key_locations包含3-4个对象，factions包含2-3个对象。

## 字段详细要求

### core_rules（核心世界规则，3条）
每条规则包含三个字段：
1. **rule_content**：30-50字，世界的客观规律或运行机制
2. **impact_on_protagonist**：20-30字，规则如何影响主角
3. **conflict_potential**：20-30字，可能引发的戏剧冲突

### key_locations（关键地点，3-4个）
每个地点包含五个字段：
1. **name**：3-8字，地点名称（简洁有辨识度）
2. **visual_description**：30-40字，2-3个核心视觉元素
3. **functional_role**：15-20字，场景功能定位
4. **emotional_tone**：10-15字，情感氛围
5. **plot_usage**：30-40字，在剧情中的作用

### factions（主要势力，2-3个）
每个势力包含五个字段：
1. **name**：3-8字，势力名称（简洁有辨识度）
2. **core_interest**：20-30字，该势力的核心诉求
3. **power_level**：15-20字，在世界中的地位
4. **representative**：20-30字，至少1个关键角色及其特点
5. **relation_to_protagonist**：30-40字，与主角关系的演变

## 特别约束
- **数量限制**：core_rules必须3条，key_locations必须3-4个，factions必须2-3个
- **字数控制**：严格遵守各字段字数限制，避免生成过长内容
- **一致性**：所有设定必须与基础信息和故事梗概保持一致
- **可执行性**：设定要具体到可以指导章节创作
- **JSON完整性**：确保生成完整的JSON，正确闭合所有括号

## 输出检查清单
生成JSON后，内部检查：
- ✅ 所有数组长度是否符合要求？
- ✅ 每个对象是否包含所有必需字段？
- ✅ 每个字段内容是否符合字数限制？
- ✅ 所有设定是否与基础信息和故事梗概一致？
- ✅ JSON是否完整（所有括号正确闭合）？

## 禁止事项
❌ 输出任何JSON之外的内容
❌ 使用占位符（"待定"、"TBD"等）
❌ 生成抽象或模糊的描述
❌ 超出字数限制
❌ 生成不完整的JSON

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt
    user_prompt = f"""## 基础信息
{basic_info}

## 故事梗概
{synopsis}

请基于以上信息，生成符合要求的世界观设定JSON。"""

    return system_prompt, user_prompt
