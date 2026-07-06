"""
我的第一个 Agent —— 手写 ReAct 循环，无框架
============================================
这份代码演示 agent 的本质：一个循环。
模型不会自己算数、也不知道现在几点，但它能"决定要调用哪个工具"，
我们（代码）负责真正执行工具、把结果喂回去，如此往复，直到它得出答案。

运行前：
  1. 安装依赖：  pip install openai
  2. 在下面填入你的 API key，并选择你用的服务商（Groq 或 Gemini）
  3. 运行：      python my_first_agent.py
"""

from openai import OpenAI
import json
import datetime
import os
# ============================================================
# 第 1 步：配置。你用哪家就留哪家，把另一家整段注释掉。
# ============================================================

# --- 方案 A：Groq（推荐，速度快，OpenAI 兼容）---
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),   # ← 改成这样
    base_url="https://api.groq.com/openai/v1",
)
MODEL = "llama-3.3-70b-versatile"

# --- 方案 B：Google Gemini（如果你用的是这个，就把上面 A 注释掉，解开下面）---
# client = OpenAI(
#     api_key="在这里粘贴你的_GEMINI_KEY",
#     base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
# )
# MODEL = "gemini-2.5-flash"


# ============================================================
# 第 2 步：定义工具。工具就是普通的 Python 函数。
# ============================================================

def calculator(expression: str) -> str:
    """计算一个数学表达式，比如 '(3 + 5) * 2'。"""
    try:
        # 用空的 builtins 做一个受限的 eval，避免执行危险代码。
        # （学习够用；正式项目里应该用更严格的解析器。）
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"计算出错：{e}"
def get_weather(city:str)->str:
    return f"{city}今天:晴，气温25度，风力3级。"

def get_current_time(_: str = "") -> str:
    """返回当前的日期和时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 把函数名映射到函数本身，方便循环里按名字调用
AVAILABLE_TOOLS = {
    "calculator": calculator,
    "get_current_time": get_current_time,
    "get_weather":get_weather,
}

# 告诉模型有哪些工具可用（这段描述是模型"看得到"的说明书）
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算一个数学表达式。当需要做算术时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式，例如 '(3 + 5) * 2'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间。当被问到现在几点、今天几号时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type":"function",
        "function":{
            "name":"get_weather",
            "description":"获取指定的天气信息，当被问到天气时使用。因为没法联网，所以返回的是模拟数据。",
            "parameters":{
                "type":"object",
                "properties":{
                    "city":{
                        "type":"string",
                        "description":"被查询天气的城市名称，例如 '北京'、'上海'、'广州' 等。"
                    }
                }
            }
        }
    }
]


# ============================================================
# 第 3 步：Agent 主循环 —— 这就是 agent 的"心脏"
# ============================================================

def run_agent(user_question: str, max_steps: int = 5):
    print(f"\n🧑 用户：{user_question}\n")

    # messages 是对话历史，我们会不断往里追加内容
    messages = [
        {
            "role": "system",
            "content": "你是一个乐于助人的助手。只有当问题真正涉及算数或时间时才调用工具；如果是普通聊天或自我介绍，直接回答，不要调用任何工具。",
        },
        {"role": "user", "content": user_question},
    ]

    # 核心循环：最多循环 max_steps 次，防止无限循环
    for step in range(max_steps):
        print(f"--- 第 {step + 1} 轮思考 ---")

        # (1) 让模型思考：它要么直接回答，要么决定调用某个工具
        # 开源模型偶尔会把工具调用的格式写错，被服务器拒绝(tool_use_failed)。
        # 这属于间歇性抽风，重试几次通常就好，所以这里加个简单的重试。
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                )
                break  # 成功就跳出重试
            except Exception as e:
                print(f"   （第 {attempt + 1} 次请求失败，重试中… {type(e).__name__}）")
        if response is None:
            print("\n⚠️ 连续重试 3 次仍失败，跳过这个问题。\n")
            return None
        message = response.choices[0].message

        # (2) 如果模型没有要求调用工具，说明它已经能回答了 —— 循环结束
        if not message.tool_calls:
            # 清理开源模型偶尔漏出来的残留标记
            clean = (message.content or "").replace("<function>", "").replace("</function>", "").strip()
            print(f"\n🤖 Agent：{clean}\n")
            return clean

        # (3) 模型决定调用工具。把它这一步的决定加进历史
        messages.append(message)

        # (4) 逐个执行它想调用的工具，把结果喂回去
        for tool_call in message.tool_calls:
            # ↓↓↓ 新增：把模型返回的原始结构原样打印出来看看 ↓↓↓
            #print("\n========= 🔬 透视：模型返回的原始工具调用 =========")
            #print("tool_call 整体类型：", type(tool_call))
            #print("tool_call.id            =", tool_call.id)
            #print("tool_call.function.name =", repr(tool_call.function.name))
            #print("tool_call.function.arguments =", repr(tool_call.function.arguments))
            #print("   ↑ 注意：arguments 是一段【字符串】，两边有引号")
            #print("=====================================================\n")
            # ↑↑↑ 新增结束 ↑↑↑

            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}") or {}
            print("经过 json.loads 之后，args 变成【字典】：", args, "  类型：", type(args))
            # ... 后面你原来的代码不变
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}") or {}
            print(f"🔧 模型决定调用工具：{name}，参数：{args}")

            # 真正执行这个 Python 函数
            tool_function = AVAILABLE_TOOLS[name]
            result = tool_function(**args)
            print(f"   工具返回：{result}")

            # 把工具结果作为一条新消息加进历史，让模型下一轮能看到
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
        # 循环回到 (1)，模型带着工具结果继续思考

    print("\n⚠️ 达到最大步数仍未得出答案。\n")
    return None


# ============================================================
# 第 4 步：试跑几个问题
# ============================================================

if __name__ == "__main__":
    run_agent("现在几点了？")
    run_agent("如果一件商品原价 240 元，打七五折，再减 30 元，最后多少钱？")
    run_agent("你好，你是谁？")  # 这个不需要工具，模型会直接回答
    run_agent("北京今天天气怎么样？")
