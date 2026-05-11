"""
Face++ 旷视肤质分析 API 服务
用于分析用户上传的照片，获取详细的肤质数据

降级策略:
1. 优先使用 face++ 外部 API
2. face++ 不可用时，使用系统 AI 分析
3. AI 不可用时，使用保底规则
"""

import httpx
import json
import base64
from typing import Optional
from dataclasses import dataclass
from app.core.config import get_settings

settings = get_settings()

# Face++ API 配置
FACEPLUSPLUS_API_KEY = "zXtMmfUa8_ctwb4u8G9oP4V8cTTFEc3h"
FACEPLUSPLUS_API_SECRET = "vmCWTOAl1hyINuLjnv1-ISm8j4Ih9vxn"
FACEPLUSPLUS_API_URL = "https://api-cn.faceplusplus.com/facepp/v1/skinanalyze"


@dataclass
class SkinAnalysisResult:
    """肤质分析结果"""
    # 分析来源: faceplusplus / ai / fallback
    source: str
    
    # 皮肤类型: 0=油性, 1=干性, 2=中性, 3=混合性
    skin_type: int
    skin_type_name: str
    
    # 各项指标 (0=无问题, 1=有问题)
    dark_circle: int  # 黑眼圈
    eye_pouch: int  # 眼袋
    forehead_wrinkle: int  # 额头皱纹
    nasolabial_fold: int  # 法令纹
    crows_feet: int  # 鱼尾纹
    glabella_wrinkle: int  # 眉间皱纹
    eye_finelines: int  # 眼部细纹
    
    # 皮肤问题
    acne: int  # 痘痘
    blackhead: int  # 黑头
    skin_spot: int  # 皮肤斑点
    mole: int  # 痣
    
    # 毛孔状况 (0=细腻, 1=略粗)
    pores_forehead: int  # 额头毛孔
    pores_left_cheek: int  # 左脸颊毛孔
    pores_right_cheek: int  # 右脸颊毛孔
    pores_jaw: int  # 下巴毛孔
    left_eyelids: int  # 左眼皮
    right_eyelids: int  # 右眼皮
    
    # 综合评分 (0-100)
    skin_score: float
    
    # 问题列表
    issues: list[str]
    
    # 护理建议
    suggestions: list[str]


# 皮肤类型映射
SKIN_TYPE_MAP = {
    0: "油性",
    1: "干性",
    2: "中性",
    3: "混合性"
}

# 问题描述映射
ISSUE_MAP = {
    "dark_circle": "黑眼圈",
    "eye_pouch": "眼袋",
    "forehead_wrinkle": "额头皱纹",
    "nasolabial_fold": "法令纹",
    "crows_feet": "鱼尾纹",
    "glabella_wrinkle": "眉间皱纹",
    "eye_finelines": "眼部细纹",
    "acne": "痘痘",
    "blackhead": "黑头",
    "skin_spot": "皮肤斑点",
    "mole": "痣",
    "pores_forehead": "额头毛孔粗大",
    "pores_left_cheek": "左脸颊毛孔粗大",
    "pores_right_cheek": "右脸颊毛孔粗大",
    "pores_jaw": "下巴毛孔粗大",
}

# 护理建议映射
SUGGESTION_MAP = {
    "dark_circle": "保证充足睡眠，使用眼霜，冷敷眼部",
    "eye_pouch": "减少盐分摄入，使用紧致眼霜，睡前少喝水",
    "forehead_wrinkle": "注意防晒，使用抗皱精华，保持面部表情放松",
    "nasolabial_fold": "使用抗皱精华，做面部按摩，注意防晒",
    "crows_feet": "使用眼霜，做眼部按摩，避免过度眯眼",
    "glabella_wrinkle": "放松眉头，使用抗皱产品，减少皱眉习惯",
    "eye_finelines": "使用眼霜，保持眼部湿润，避免过度用眼",
    "acne": "注意清洁，少吃油腻食物，使用祛痘产品",
    "blackhead": "定期深层清洁，使用收敛水，不要用手挤",
    "skin_spot": "注意防晒，使用美白精华，定期去角质",
    "pores_forehead": "定期深层清洁，使用收敛水，控油",
    "pores_left_cheek": "定期深层清洁，使用收敛水，注意补水",
    "pores_right_cheek": "定期深层清洁，使用收敛水，注意补水",
    "pores_jaw": "定期深层清洁，使用收敛水，注意清洁",
}


def _calculate_skin_score(result: dict) -> tuple[float, list[str], list[str]]:
    """计算肤质综合评分，返回 (评分, 问题列表, 建议列表)"""
    score = 100.0
    issues = []
    suggestions = []
    
    # 皱纹类问题扣分
    wrinkle_fields = [
        "forehead_wrinkle", "nasolabial_fold", "crows_feet",
        "glabella_wrinkle", "eye_finelines"
    ]
    for field in wrinkle_fields:
        if result.get(field, {}).get("value", 0) == 1:
            score -= 5
            issues.append(ISSUE_MAP.get(field, field))
            suggestions.append(SUGGESTION_MAP.get(field, ""))
    
    # 黑眼圈/眼袋扣分
    if result.get("dark_circle", {}).get("value", 0) == 1:
        score -= 8
        issues.append("黑眼圈")
        suggestions.append(SUGGESTION_MAP["dark_circle"])
    
    if result.get("eye_pouch", {}).get("value", 0) == 1:
        score -= 5
        issues.append("眼袋")
        suggestions.append(SUGGESTION_MAP["eye_pouch"])
    
    # 皮肤问题扣分
    if result.get("acne", {}).get("value", 0) == 1:
        score -= 10
        issues.append("痘痘")
        suggestions.append(SUGGESTION_MAP["acne"])
    
    if result.get("blackhead", {}).get("value", 0) == 1:
        score -= 5
        issues.append("黑头")
        suggestions.append(SUGGESTION_MAP["blackhead"])
    
    if result.get("skin_spot", {}).get("value", 0) == 1:
        score -= 5
        issues.append("皮肤斑点")
        suggestions.append(SUGGESTION_MAP["skin_spot"])
    
    # 毛孔问题扣分
    pore_fields = ["pores_forehead", "pores_left_cheek", "pores_right_cheek", "pores_jaw"]
    for field in pore_fields:
        if result.get(field, {}).get("value", 0) == 1:
            score -= 3
            issues.append(ISSUE_MAP.get(field, field))
            suggestions.append(SUGGESTION_MAP.get(field, ""))
    
    # 确保分数在 0-100 之间
    score = max(0, min(100, score))
    
    # 去重建议
    suggestions = list(dict.fromkeys(suggestions))
    
    return score, issues, suggestions


async def _call_faceplus_api(image_path: str) -> Optional[SkinAnalysisResult]:
    """调用 face++ API 分析肤质"""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                FACEPLUSPLUS_API_URL,
                data={
                    "api_key": FACEPLUSPLUS_API_KEY,
                    "api_secret": FACEPLUSPLUS_API_SECRET,
                },
                files={
                    "image_file": ("photo.jpg", image_data, "image/jpeg")
                }
            )
            
            data = response.json()
            
            # 检查是否有错误
            if "error" in data:
                print(f"[face++] API 错误: {data['error'].get('message', '未知错误')}")
                return None
            
            result = data.get("result", {})
            if not result:
                print("[face++] 返回数据为空")
                return None
            
            # 计算综合评分
            skin_score, issues, suggestions = _calculate_skin_score(result)
            
            # 提取皮肤类型
            skin_type = result.get("skin_type", {}).get("skin_type", 2)
            
            return SkinAnalysisResult(
                source="faceplusplus",
                skin_type=skin_type,
                skin_type_name=SKIN_TYPE_MAP.get(skin_type, "未知"),
                dark_circle=result.get("dark_circle", {}).get("value", 0),
                eye_pouch=result.get("eye_pouch", {}).get("value", 0),
                forehead_wrinkle=result.get("forehead_wrinkle", {}).get("value", 0),
                nasolabial_fold=result.get("nasolabial_fold", {}).get("value", 0),
                crows_feet=result.get("crows_feet", {}).get("value", 0),
                glabella_wrinkle=result.get("glabella_wrinkle", {}).get("value", 0),
                eye_finelines=result.get("eye_finelines", {}).get("value", 0),
                acne=result.get("acne", {}).get("value", 0),
                blackhead=result.get("blackhead", {}).get("value", 0),
                skin_spot=result.get("skin_spot", {}).get("value", 0),
                mole=result.get("mole", {}).get("value", 0),
                pores_forehead=result.get("pores_forehead", {}).get("value", 0),
                pores_left_cheek=result.get("pores_left_cheek", {}).get("value", 0),
                pores_right_cheek=result.get("pores_right_cheek", {}).get("value", 0),
                pores_jaw=result.get("pores_jaw", {}).get("value", 0),
                left_eyelids=result.get("left_eyelids", {}).get("value", 0),
                right_eyelids=result.get("right_eyelids", {}).get("value", 0),
                skin_score=skin_score,
                issues=issues,
                suggestions=suggestions,
            )
    except Exception as e:
        print(f"[face++] 调用异常: {e}")
        return None


async def _call_ai_analysis(image_path: str) -> Optional[SkinAnalysisResult]:
    """使用系统 AI 分析肤质（降级方案）"""
    try:
        # 读取图片并转为 base64
        with open(image_path, 'rb') as f:
            image_data = f.read()
        b64 = base64.b64encode(image_data).decode('utf-8')
        b64_url = f"data:image/jpeg;base64,{b64}"
        
        prompt = """请分析这张面部照片的肤质状况，返回 JSON 格式：

{
  "skin_type": 0-3 (0=油性, 1=干性, 2=中性, 3=混合性),
  "dark_circle": 0或1 (黑眼圈),
  "eye_pouch": 0或1 (眼袋),
  "acne": 0或1 (痘痘),
  "blackhead": 0或1 (黑头),
  "skin_spot": 0或1 (斑点),
  "pores_forehead": 0或1 (额头毛孔粗大),
  "pores_left_cheek": 0或1 (左脸颊毛孔粗大),
  "pores_right_cheek": 0或1 (右脸颊毛孔粗大),
  "skin_score": 0-100 (综合肤质评分)
}

只返回 JSON，不要其他内容。"""

        messages = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": b64_url}},
            {"type": "text", "text": prompt}
        ]}]
        
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": messages,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
            )
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            # 构建问题列表
            issues = []
            suggestions = []
            issue_fields = {
                "dark_circle": "黑眼圈",
                "eye_pouch": "眼袋",
                "acne": "痘痘",
                "blackhead": "黑头",
                "skin_spot": "皮肤斑点",
                "pores_forehead": "额头毛孔粗大",
                "pores_left_cheek": "左脸颊毛孔粗大",
                "pores_right_cheek": "右脸颊毛孔粗大",
            }
            
            for field, name in issue_fields.items():
                if result.get(field, 0) == 1:
                    issues.append(name)
                    suggestions.append(SUGGESTION_MAP.get(field, ""))
            
            skin_type = result.get("skin_type", 2)
            
            return SkinAnalysisResult(
                source="ai",
                skin_type=skin_type,
                skin_type_name=SKIN_TYPE_MAP.get(skin_type, "未知"),
                dark_circle=result.get("dark_circle", 0),
                eye_pouch=result.get("eye_pouch", 0),
                forehead_wrinkle=result.get("forehead_wrinkle", 0),
                nasolabial_fold=result.get("nasolabial_fold", 0),
                crows_feet=result.get("crows_feet", 0),
                glabella_wrinkle=result.get("glabella_wrinkle", 0),
                eye_finelines=result.get("eye_finelines", 0),
                acne=result.get("acne", 0),
                blackhead=result.get("blackhead", 0),
                skin_spot=result.get("skin_spot", 0),
                mole=result.get("mole", 0),
                pores_forehead=result.get("pores_forehead", 0),
                pores_left_cheek=result.get("pores_left_cheek", 0),
                pores_right_cheek=result.get("pores_right_cheek", 0),
                pores_jaw=result.get("pores_jaw", 0),
                left_eyelids=result.get("left_eyelids", 0),
                right_eyelids=result.get("right_eyelids", 0),
                skin_score=result.get("skin_score", 70),
                issues=issues,
                suggestions=suggestions,
            )
    except Exception as e:
        print(f"[AI肤质分析] 分析异常: {e}")
        return None


def _get_fallback_result() -> SkinAnalysisResult:
    """保底规则：返回默认的肤质分析结果"""
    return SkinAnalysisResult(
        source="fallback",
        skin_type=2,
        skin_type_name="中性",
        dark_circle=0,
        eye_pouch=0,
        forehead_wrinkle=0,
        nasolabial_fold=0,
        crows_feet=0,
        glabella_wrinkle=0,
        eye_finelines=0,
        acne=0,
        blackhead=0,
        skin_spot=0,
        mole=0,
        pores_forehead=0,
        pores_left_cheek=0,
        pores_right_cheek=0,
        pores_jaw=0,
        left_eyelids=0,
        right_eyelids=0,
        skin_score=75.0,
        issues=[],
        suggestions=["保持良好的护肤习惯"],
    )


async def analyze_skin(image_path: str) -> SkinAnalysisResult:
    """
    分析图片中的肤质
    
    降级策略:
    1. 优先使用 face++ 外部 API
    2. face++ 不可用时，使用系统 AI 分析
    3. AI 不可用时，使用保底规则
    
    Args:
        image_path: 图片文件路径 (如 uploads/xxx.jpg)
    
    Returns:
        SkinAnalysisResult (包含 source 字段标识分析来源)
    """
    # 1. 尝试 face++ API
    print("[肤质分析] 尝试 face++ API...")
    result = await _call_faceplus_api(image_path)
    if result:
        print(f"[肤质分析] face++ API 成功，评分: {result.skin_score}")
        return result
    
    # 2. 降级到系统 AI
    print("[肤质分析] face++ API 不可用，降级到系统 AI...")
    result = await _call_ai_analysis(image_path)
    if result:
        print(f"[肤质分析] 系统 AI 成功，评分: {result.skin_score}")
        return result
    
    # 3. 降级到保底规则
    print("[肤质分析] 系统 AI 不可用，使用保底规则")
    return _get_fallback_result()


def generate_skin_task(skin_result: SkinAnalysisResult) -> str:
    """
    根据肤质分析结果生成护肤任务
    
    Args:
        skin_result: 肤质分析结果
    
    Returns:
        护肤任务描述
    """
    if not skin_result.issues:
        # 没有明显问题，根据皮肤类型生成任务
        skin_type = skin_result.skin_type_name
        if skin_type == "油性":
            return "使用控油洁面乳清洁面部，配合清爽型保湿"
        elif skin_type == "干性":
            return "使用温和洁面乳，配合滋润型保湿霜"
        elif skin_type == "混合性":
            return "T区控油清洁，两颊重点保湿"
        else:
            return "认真护肤一次，保持良好状态"
    
    # 根据主要问题生成任务
    main_issue = skin_result.issues[0]
    
    task_map = {
        "黑眼圈": "使用眼霜按摩眼周5分钟，晚上11点前入睡",
        "眼袋": "冷敷眼部10分钟，减少睡前饮水",
        "额头皱纹": "使用抗皱精华按摩额头，注意防晒",
        "法令纹": "做面部按摩提升，使用抗皱精华",
        "鱼尾纹": "使用眼霜按摩眼周，避免过度眯眼",
        "眉间皱纹": "放松眉头，使用抗皱精华按摩",
        "眼部细纹": "使用眼霜轻拍眼周，保持眼部湿润",
        "痘痘": "认真清洁面部，使用祛痘产品",
        "黑头": "使用清洁面膜，配合收敛水",
        "皮肤斑点": "使用美白精华，注意防晒",
        "额头毛孔粗大": "使用收敛水湿敷额头5分钟",
        "左脸颊毛孔粗大": "使用收敛水湿敷脸颊5分钟",
        "右脸颊毛孔粗大": "使用收敛水湿敷脸颊5分钟",
        "下巴毛孔粗大": "使用清洁面膜，配合收敛水",
    }
    
    return task_map.get(main_issue, "认真护肤一次")


def get_source_display(source: str) -> str:
    """获取分析来源的显示文本"""
    source_map = {
        "faceplusplus": "外部API (face++)",
        "ai": "系统AI分析",
        "fallback": "保底规则",
    }
    return source_map.get(source, source)
