"""第4步：生成角色
基于 blueprint.md 的详细字段定义
"""
from typing import Dict, Any, Tuple


def build_prompt(basic_info: Dict[str, Any], synopsis: str, world_setting: Dict[str, Any]) -> Tuple[str, str]:
    """
    构建第4步的prompt（直接返回system和user prompt）

    Args:
        basic_info: 基础信息
        synopsis: 故事梗概
        world_setting: 世界观设定

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 构建System Prompt
    system_prompt = """# 角色生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责基于基础信息、梗概和世界观，生成详细的角色列表。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象：

```json
{{
  "characters": [
    {{
      "name": "string - 角色名字，2-4个字，符合世界观风格",
      "identity": "string - 身份标签，如'主角'/'女主'/'前期主要对手'",
      "personality": "string - 性格描述，包含3-5个核心特质关键词+行为模式+性格反差点",
      "goals": "string - 目标层次，包含表面目标+深层动机+与主角目标的关系",
      "abilities": "string - 能力量化，包含当前实力等级+核心技能+战力定位+成长潜力",
      "relationship_to_protagonist": "string - 关系演变，包含初识情境+关系发展+情感张力+对主角的影响"
    }}
  ]
}}
```

## 字段详细要求

### name（角色名字）
- 2-4个字，符合世界观风格

### identity（身份标签）
建议标签：主角、女主、前期主要对手、导师型配角、功能性路人

### personality（性格描述）
必须包含三个要素：
1. 3-5个核心特质关键词
2. 一句话行为模式
3. 一个性格反差点

### goals（目标层次）
必须包含三个要素：
1. 表面目标：角色自己认为的目标
2. 深层动机：真正驱动的原因
3. 与主角目标的关系：如何互动

### abilities（能力量化）
必须包含四个要素：
1. 当前实力等级：用世界观体系描述
2. 核心技能：2-3个代表性能力
3. 战力定位：在同辈中的排位
4. 成长潜力：天赋上限

### relationship_to_protagonist（关系演变）
必须包含四个要素：
1. 初识情境：如何认识，第一印象
2. 关系发展：前期、中期、后期各阶段
3. 情感张力：矛盾点或化学反应
4. 对主角的影响：如何改变主角

## 角色数量控制
- 主角：1名，完整设定
- 核心配角：2-3名，详细设定
- 次要角色：1-2名，功能性，简化设定
- 总计不超过5名

## 输出检查清单
✅ 每个角色是否有完整的6个字段？
✅ 主角是否在第一个？
✅ 角色数量是否不超过5个？
✅ 是否有至少一个角色与主角有复杂关系？

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt
    user_prompt = f"""## 基础信息
{basic_info}

## 故事梗概
{synopsis}

## 世界观设定
{world_setting}

请基于以上信息，生成符合要求的角色列表JSON。"""

    return system_prompt, user_prompt
