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
import requests
import sqlite3

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
    try:
        # 1. 发请求（format=j1 表示要 JSON）
         url = f"https://wttr.in/{city}?format=j1"
         response = requests.get(url, timeout=10)
         data = response.json()
        # 2. 从返回数据里取出温度和天气描述
         temp = data["current_condition"][0]["temp_C"]
         desc = data["current_condition"][0]["weatherDesc"][0]["value"]
         return f"{city}的天气是{desc}，温度是{temp}°C。"
    except Exception as e:
        return f"查询天气出错:{e}"
def get_forecast(city:str, days:int = 3)->str:
    try:
        url = f"https://wttr.in/{city}?format=j1"
        response = requests.get(url, timeout=10)
        data = response.json()
        result = f"{city}未来{days}天预报:\n"
        for day in data["weather"][:days]:
            date = day["date"]
            max_t = day["maxtempC"]
            min_t = day["mintempC"]
            result += f"{date}:最高{max_t}°C，最低{min_t}°C\n"
        return result
    except Exception as e:
        return f"查询天气预报出错:{e}"
def get_current_time(_: str = "") -> str:
    """返回当前的日期和时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def query_database(sql: str) -> str:
    """执行一句 SQL 查询（只允许 SELECT 查询）。"""
    # 安全护栏：只允许查询，禁止任何修改/删除操作
    if not sql.strip().upper().startswith("SELECT"):
        return "拒绝执行：出于安全考虑，只允许 SELECT 查询。"
    try:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return str(rows)
    except Exception as e:
        return f"查询出错:{e}"

# 把函数名映射到函数本身，方便循环里按名字调用
AVAILABLE_TOOLS = {
    "calculator": calculator,
    "get_current_time": get_current_time,
    "get_weather":get_weather,
    "query_database":query_database,
    "get_forecast":get_forecast
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
            "description":"获取指定的天气信息，当被问到天气时使用。请使用工具获取天气信息，而不是直接回答。",
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
    },
    {
        "type":"function",
        "function":{
            "name":"query_database",
            "description":"这是一个查询用户SQL数据库的工具,表名是users，字段里有id, name, city, age, 当被问到数据库相关问题时使用。请使用工具查询数据库，而不是直接回答。",
            "parameters":{
                "type":"object",
                "properties":{
                    "sql":{
                        "type":"string",
                        "description":"要执行的SQL查询语句，例如 'SELECT * FROM users WHERE age > 30;'"
                    }
                },
                "required":["sql"]
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name":"get_forecast",
            "description":"获取指定城市的天气预报，当被问到未来几天的天气时使用。请使用工具获取天气预报，而不是直接回答。",
            "parameters":{
                "type":"object",
                "properties":{
                    "city":{
                        "type":"string",
                        "description":"被查询天气预报的城市名称，例如 '北京'、'上海'、'广州' 等。"
                    },
                    "days":{
                        "type":"integer",
                        "description":"要查询的未来几天的天气预报，默认为3天。"
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
            "content": ""你是一个乐于助人的助手。调用工具拿到结果后，如果信息已经足够回答用户，就直接回答，不要重复调用同一个工具。"",
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
    print("你好！我是你的助手，可以查天气、算数、查用户数据库。输入 quit 退出。")
    while True:
        question = input("\n请输入你的问题:")
        if question.strip().lower() in ("quit", "exit", "退出"):
            print("再见!")
            break
        run_agent(question)
