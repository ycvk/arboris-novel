"""第5步：生成角色关系
基于 blueprint.md 的详细字段定义
"""
from typing import List, Dict, Any, Tuple


def build_prompt(characters: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    构建第5步的prompt（直接返回system和user prompt）

    Args:
        characters: 角色列表

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 格式化角色列表
    char_text = "\n".join([
        f"- {c.get('name', 'Unknown')} ({c.get('identity', 'Unknown')})"
        for c in characters
    ])

    # 构建System Prompt
    system_prompt = """# 关系生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责基于角色列表，生成角色之间的关系网络。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象：

```json
{{
  "relationships": [
    {{
      "character_from": "string - 角色A名字（必须在characters中存在）",
      "character_to": "string - 角色B名字（必须在characters中存在）",
      "description": "string - 50-80字，说明：当前关系状态+关系根源+动态变化+对剧情的作用"
    }}
  ]
}}
```

## 字段详细要求

### character_from 和 character_to
- 必须是characters列表中存在的角色名字
- 区分先后顺序（谁->谁）

### description（关系描述）
必须包含四个要素：
1. **当前关系状态**：具体关系类型
2. **关系的根源**：历史原因
3. **动态变化**：如何发展
4. **对剧情的作用**：创造什么张力

## 关系网络要求
- 至少描述5条relationship
- 每个核心配角必须与主角有关系条目
- 主角与其他所有重要角色都要有关系

## 输出检查清单
✅ 是否有至少5条关系？
✅ 每个核心配角是否都与主角有关系？
✅ 所有角色名是否在characters中存在？
✅ 关系描述是否具体可操作？

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt
    user_prompt = f"""## 角色列表
{char_text}

请基于以上角色列表，生成符合要求的角色关系JSON。"""

    return system_prompt, user_prompt
