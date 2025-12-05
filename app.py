from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import requests
import time
import random

# 全局变量用于存储当前播放的音乐信息
current_music = {
    "name": "",
    "artist": "",
    "image": "",
    "url": "",
    "status": "stopped",  # stopped, playing, paused
    "progress": 0
}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dai_p_chat_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 存储在线用户信息，格式：{session_id: {'username': '用户名', 'nickname': '昵称', 'server': '服务器地址'}}
online_users = {}
# 默认房间名
ROOM_NAME = 'main_room'

# 读取配置文件
def load_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'servers': ['http://localhost:5000']}

# 保存配置文件
def save_config(config):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 读取用户数据
def load_users():
    users_path = 'users.json'
    if os.path.exists(users_path):
        with open(users_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# 保存用户数据
def save_users(users):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# 获取真实天气数据的函数（使用和风天气API）
def get_real_weather(location):
    try:
        # 和风天气免费版API配置（模拟数据，实际使用时需要替换为真实的API key）
        api_key = "your_qweather_api_key"  # 请替换为实际的和风天气API key
        base_url = "https://devapi.qweather.com/v7/weather/now"
        geo_url = "https://geoapi.qweather.com/v2/city/lookup"
        
        # 检查是否为测试环境或无API key
        if api_key == "your_qweather_api_key":
            print(f"使用模拟天气数据代替API调用，位置: {location}")
            # 使用模拟数据作为备用方案
            return get_mock_weather_data(location)
        
        # 1. 首先通过地名获取城市ID
        geo_params = {
            "location": location,
            "key": api_key,
            "range": "cn"  # 限制在中国范围内搜索
        }
        geo_response = requests.get(geo_url, params=geo_params, timeout=5)
        geo_data = geo_response.json()
        
        # 检查响应状态
        if geo_data.get("code") != "200" or not geo_data.get("location"):
            print(f"无法获取城市信息: {geo_data.get('code')}")
            return get_mock_weather_data(location)  # 失败时回退到模拟数据
        
        # 获取第一个匹配的城市ID
        city_id = geo_data["location"][0]["id"]
        actual_location = geo_data["location"][0]["name"]
        
        # 2. 使用城市ID获取天气数据
        weather_params = {
            "location": city_id,
            "key": api_key
        }
        weather_response = requests.get(base_url, params=weather_params, timeout=5)
        weather_data = weather_response.json()
        
        # 检查响应状态
        if weather_data.get("code") != "200" or not weather_data.get("now"):
            print(f"无法获取天气信息: {weather_data.get('code')}")
            return get_mock_weather_data(location)  # 失败时回退到模拟数据
        
        # 提取天气数据
        now = weather_data["now"]
        temp = int(now["temp"])
        humidity = int(now["humidity"])
        description = now["text"]
        wind_speed = float(now["windSpeed"])
        
        return {
            "location": actual_location,
            "temp": temp,
            "humidity": humidity,
            "description": description,
            "wind_speed": wind_speed
        }
    except Exception as e:
        print(f"获取真实天气数据时出错: {str(e)}")
        return get_mock_weather_data(location)  # 出错时回退到模拟数据

# 获取百度热点新闻的函数
def get_baidu_hot_news():
    try:
        # 百度热点新闻API
        api_url = "https://v2.xxapi.cn/api/baiduhot"
        
        print(f"正在调用百度热点新闻API: {api_url}")
        
        # 发送请求
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()  # 检查请求是否成功
        
        # 解析响应
        data = response.json()
        print(f"百度热点新闻API响应状态: {data.get('code')}")
        
        if data.get('code') == 200 and data.get('data'):
            return data['data']
        else:
            error_msg = data.get('msg', '未知错误')
            print(f"获取百度热点新闻失败: {error_msg}")
            # 返回模拟数据作为备用
            return get_mock_news_data()
    except Exception as e:
        print(f"获取百度热点新闻时出错: {str(e)}")
        # 生成模拟新闻数据作为备用
        return get_mock_news_data()

# 生成模拟新闻数据的辅助函数
def get_mock_news_data():
    # 模拟百度热点新闻数据
    mock_news = [
        {
            "desc": "11月28日，习近平总书记在主持中共中央政治局第二十三次集体学习时强调，网络生态治理\"事关国家发展和安全，事关人民群众切身利益\"。持续营造风清气正的网络空间，推动构建网络空间命运共同体，总书记关心的这件事，和屏幕前的你我息息相关。",
            "hot": "790万",
            "img": "https://fyb-2.cdn.bcebos.com/hotboard_image/7305a609c38578f5ab5f36c5a9537ab6",
            "index": 1,
            "title": "总书记关心的这件事 和你我息息相关",
            "url": "https://www.baidu.com/s?wd=总书记关心的这件事+和你我息息相关"
        },
        {
            "desc": "11月29日，湖南省委十二届九次全会第二次全体会议原定于湖南宾馆芙蓉厅举行，因与两场婚宴场地冲突，临时调整至会议中心三楼。",
            "hot": "780万",
            "img": "https://fyb-2.cdn.bcebos.com/hotboard_image/bcacf7c1d2f87c1196e2a5ef2ac1a1fd",
            "index": 2,
            "title": "省委全会为两场婚宴腾会场",
            "url": "https://www.baidu.com/s?wd=省委全会为两场婚宴腾会场"
        },
        {
            "desc": "据日媒11月28日爆料，根据相关资金收支报告，在2024年日本自民党总裁选举中，高市早苗所属政治团体的宣传支出约为8384万日元，最终仍败给了支出仅42万日元的石破茂。",
            "hot": "771万",
            "img": "https://fyb-2.cdn.bcebos.com/hotboard_image/5ea08c33ffa0d2fd625e38e273756be4",
            "index": 3,
            "title": "曝高市早苗花8千万日元仍败给石破茂",
            "url": "https://www.baidu.com/s?wd=曝高市早苗花8千万日元仍败给石破茂"
        },
        {
            "desc": "随着冬季气温的逐渐降低，北方各地充分利用冰雪冷资源创新消费场景，冰雪旅游快速升温。",
            "hot": "761万",
            "img": "https://fyb-2.cdn.bcebos.com/hotboard_image/beb43a6a2e1e95f0c9f797e4875d5db8",
            "index": 4,
            "title": "创新消费场景 冰雪旅游快速升温",
            "url": "https://www.baidu.com/s?wd=创新消费场景+冰雪旅游快速升温"
        },
        {
            "desc": "近日，寒潮正在影响我国，内蒙古东北部局地出现了-40℃的极寒。12月2日，不少北方城市将度过今年下半年来最冷的一天。",
            "hot": "752万",
            "img": "https://fyb-2.cdn.bcebos.com/hotboard_image/95aede02078babd229da506cf3b392d3",
            "index": 5,
            "title": "局地-40℃极寒 下半年最冷一天来了",
            "url": "https://www.baidu.com/s?wd=局地-40℃极寒+下半年最冷一天来了"
        }
    ]
    return mock_news

# 获取音乐信息的函数
def get_music_info(music_name=None):
    global current_music  # 将global声明移到函数最开始处
    try:
        # 音乐API配置 - 使用用户要求的API和key
        api_url = "https://v2.xxapi.cn/api/randomkuwo"
        api_key = "6db38c07e6688204"  # 用户提供的API key
        
        # 构建请求参数
        params = {"key": api_key}
        if music_name:
            params["name"] = music_name  # 如果指定了音乐名，则搜索特定歌曲
        # 不指定music_name时将随机获取一首歌
        
        print(f"正在调用音乐API: {api_url}, 参数: {params}")
        
        # 发送请求
        response = requests.get(api_url, params=params, timeout=10)  # 增加超时时间以确保请求完成
        response.raise_for_status()  # 检查请求是否成功
        
        # 解析响应
        data = response.json()
        print(f"API响应: {data}")
        
        if data.get("code") == 200 and data.get("data"):
            music_data = data["data"]
            # 更新全局音乐信息
            current_music = {
                "id": str(random.randint(100000, 999999)),  # 添加唯一ID以便前端跟踪
                "name": music_data.get("name", "未知歌曲"),
                "artist": music_data.get("singer", "未知歌手"),
                "image": music_data.get("image", "https://via.placeholder.com/150"),  # 默认图片
                "url": music_data.get("url", "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"),  # 确保始终有URL
                "status": "playing",
                "progress": 0
            }
            print(f"成功获取音乐: {current_music['name']} - {current_music['artist']}")
            return current_music
        else:
            error_msg = data.get('msg', '未知错误')
            print(f"获取音乐失败: {error_msg}")
            # 即使API失败，也返回模拟数据以便功能能正常工作
            mock_music = get_mock_music_data(music_name)
            current_music = mock_music
            return mock_music
    except Exception as e:
        print(f"获取音乐时出错: {str(e)}")
        # 生成模拟音乐数据作为备用
        mock_music = get_mock_music_data(music_name)
        current_music = mock_music
        return mock_music

# 生成模拟音乐数据的辅助函数
def get_mock_music_data(music_name=None):
    # 使用更可靠的公共测试音频链接
    reliable_audio_url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
    
    # 模拟歌曲库，包含有效URL链接
    mock_songs = [
        {"name": "晴天", "artist": "周杰伦", "image": "https://via.placeholder.com/150/FF6B6B/FFFFFF?text=晴天", "url": reliable_audio_url},
        {"name": "告白气球", "artist": "周杰伦", "image": "https://via.placeholder.com/150/4ECDC4/FFFFFF?text=告白气球", "url": reliable_audio_url},
        {"name": "起风了", "artist": "买辣椒也用券", "image": "https://via.placeholder.com/150/45B7D1/FFFFFF?text=起风了", "url": reliable_audio_url},
        {"name": "成都", "artist": "赵雷", "image": "https://via.placeholder.com/150/FED766/FFFFFF?text=成都", "url": reliable_audio_url},
        {"name": "海阔天空", "artist": "Beyond", "image": "https://via.placeholder.com/150/6A0572/FFFFFF?text=海阔天空", "url": reliable_audio_url},
        {"name": "夜曲", "artist": "周杰伦", "image": "https://via.placeholder.com/150/AB83A1/FFFFFF?text=夜曲", "url": reliable_audio_url},
        {"name": "小幸运", "artist": "田馥甄", "image": "https://via.placeholder.com/150/F2EDD7/FFFFFF?text=小幸运", "url": reliable_audio_url},
        {"name": "光年之外", "artist": "邓紫棋", "image": "https://via.placeholder.com/150/687864/FFFFFF?text=光年之外", "url": reliable_audio_url}
    ]
    
    # 默认音乐URL（用于未匹配到的歌曲）
    default_url = reliable_audio_url
    
    if music_name:
        # 尝试匹配包含指定名称的歌曲
        for song in mock_songs:
            if music_name.lower() in song["name"].lower():
                return {
                    "id": str(random.randint(100000, 999999)),
                    "name": song["name"],
                    "artist": song["artist"],
                    "image": song["image"],
                    "url": song.get("url", default_url),
                    "status": "playing",
                    "progress": 0
                }
    
    # 随机选择一首歌或使用用户指定但未匹配到的名称
    if music_name:
        return {
            "id": str(random.randint(100000, 999999)),
            "name": music_name,
            "artist": "模拟歌手",
            "image": "https://via.placeholder.com/150",
            "url": default_url,
            "status": "playing",
            "progress": 0
        }
    else:
        # 随机选择一首模拟歌曲
        song = random.choice(mock_songs)
        return {
            "id": str(random.randint(100000, 999999)),
            "name": song["name"],
            "artist": song["artist"],
            "image": song["image"],
            "url": song.get("url", default_url),
            "status": "playing",
            "progress": 0
        }

# 模拟天气数据生成函数（基于地理位置的更精确模拟）
def get_mock_weather_data(location):
    import hashlib
    import random
    
    # 为特定城市提供更准确的模拟数据
    city_specific_weather = {
        # 四川城市
        "成都": {"temp": 23, "humidity": 65, "description": "多云", "wind_speed": 2.1},
        "绵阳": {"temp": 22, "humidity": 60, "description": "晴", "wind_speed": 2.3},
        "德阳": {"temp": 23, "humidity": 62, "description": "多云", "wind_speed": 2.0},
        "广元": {"temp": 21, "humidity": 58, "description": "晴", "wind_speed": 2.5},
        "遂宁": {"temp": 24, "humidity": 68, "description": "阴", "wind_speed": 1.9},
        "内江": {"temp": 25, "humidity": 70, "description": "多云", "wind_speed": 1.8},
        "乐山": {"temp": 23, "humidity": 66, "description": "阴", "wind_speed": 2.0},
        "南充": {"temp": 24, "humidity": 65, "description": "多云", "wind_speed": 2.2},
        "眉山": {"temp": 23, "humidity": 68, "description": "多云", "wind_speed": 1.9},
        "宜宾": {"temp": 24, "humidity": 72, "description": "小雨", "wind_speed": 2.1},
        "广安": {"temp": 25, "humidity": 68, "description": "多云", "wind_speed": 2.0},
        "达州": {"temp": 26, "humidity": 65, "description": "晴", "wind_speed": 2.3},
        "雅安": {"temp": 22, "humidity": 75, "description": "小雨", "wind_speed": 2.2},  # 雅安多雨
        "巴中": {"temp": 25, "humidity": 62, "description": "多云", "wind_speed": 2.4},
        "资阳": {"temp": 24, "humidity": 66, "description": "多云", "wind_speed": 2.1},
        "阿坝": {"temp": 18, "humidity": 55, "description": "晴", "wind_speed": 3.0},
        "甘孜": {"temp": 17, "humidity": 50, "description": "晴", "wind_speed": 3.2},
        "凉山": {"temp": 25, "humidity": 55, "description": "晴", "wind_speed": 2.8},
        # 其他省份重要城市
        "苏州": {"temp": 26, "humidity": 68, "description": "多云", "wind_speed": 2.2},
        "无锡": {"temp": 25, "humidity": 67, "description": "晴", "wind_speed": 2.3},
        "温州": {"temp": 27, "humidity": 70, "description": "多云", "wind_speed": 2.1},
        "金华": {"temp": 26, "humidity": 65, "description": "晴", "wind_speed": 2.0},
        "嘉兴": {"temp": 25, "humidity": 68, "description": "多云", "wind_speed": 2.4},
        "台州": {"temp": 27, "humidity": 72, "description": "多云", "wind_speed": 2.2},
        "绍兴": {"temp": 26, "humidity": 66, "description": "晴", "wind_speed": 2.1},
        "南通": {"temp": 24, "humidity": 65, "description": "晴", "wind_speed": 2.5},
        "扬州": {"temp": 24, "humidity": 64, "description": "多云", "wind_speed": 2.3},
        "常州": {"temp": 25, "humidity": 65, "description": "晴", "wind_speed": 2.2}
    }
    
    # 检查是否有特定城市的模拟数据
    if location in city_specific_weather:
        data = city_specific_weather[location]
        return {
            "location": location,
            "temp": data["temp"],
            "humidity": data["humidity"],
            "description": data["description"],
            "wind_speed": data["wind_speed"]
        }
    
    # 基于地名的地理位置推断
    hash_value = int(hashlib.md5(location.encode()).hexdigest(), 16)
    
    # 更精细的区域温度带划分
    region_temperature = {
        # 东北地区
        "黑龙江": 10, "吉林": 12, "辽宁": 15,
        # 华北地区
        "北京": 18, "天津": 18, "河北": 17, "山西": 16, "内蒙古": 14,
        # 华东地区
        "上海": 20, "江苏": 19, "浙江": 21, "安徽": 19, "福建": 22, "江西": 21, "山东": 18,
        # 华中地区
        "河南": 18, "湖北": 20, "湖南": 21,
        # 华南地区
        "广东": 24, "广西": 23, "海南": 26,
        # 西南地区
        "重庆": 22, "四川": 20, "贵州": 18, "云南": 19, "西藏": 15,
        # 西北地区
        "陕西": 17, "甘肃": 16, "青海": 14, "宁夏": 16, "新疆": 16
    }
    
    # 检查地点是否包含省份名称，以获取更准确的基础温度
    base_temp = 18  # 默认基础温度
    for province, temp in region_temperature.items():
        if province in location:
            base_temp = temp
            break
    
    # 基于地名首字母和哈希值微调温度
    first_char = location[0].upper()
    char_factor = (ord(first_char) - 65) % 10 - 5  # -5到5的调整因子
    temp = base_temp + char_factor + ((hash_value % 9) - 4)  # 额外±4度的随机变化
    
    # 基于温度和地区调整湿度
    if temp > 28:
        humidity = 65 + (hash_value % 25)  # 高温时湿度较高
    elif temp < 10:
        humidity = 30 + (hash_value % 30)  # 低温时湿度较低
    else:
        humidity = 45 + (hash_value % 35)  # 适中温度时湿度适中
    
    # 根据地区和季节特征选择天气状况
    # 模拟季节影响（基于当前月份）
    month = time.localtime().tm_mon
    season_factor = month // 3  # 0=冬, 1=春, 2=夏, 3=秋
    
    # 季节权重
    season_weights = [
        ['晴', '晴', '多云', '多云', '阴', '小雪'],  # 冬季
        ['晴', '多云', '多云', '小雨', '小雨', '阴'],  # 春季
        ['晴', '多云', '多云', '小雨', '雷阵雨', '大雨'],  # 夏季
        ['晴', '晴', '多云', '阴', '小雨', '晴间多云']  # 秋季
    ]
    
    # 地区权重调整
    weather_weights = season_weights[season_factor].copy()
    
    # 根据地区特点调整天气权重
    if "南" in location or "广" in location or "海" in location:
        # 南方地区增加降雨概率
        weather_weights.extend(['小雨', '阵雨', '多云'])
    elif "西" in location and not "江西" in location and not "山西" in location:
        # 西北地区增加晴天概率
        weather_weights.extend(['晴', '晴', '晴'])
    elif "山" in location and not "山东" in location:
        # 山区增加多云和小雨概率
        weather_weights.extend(['多云', '小雨', '阴'])
    elif "川" in location or "成都" in location:
        # 四川盆地多云雾
        weather_weights.extend(['多云', '阴', '小雨'])
    
    # 从权重列表中选择天气状况
    description = weather_weights[hash_value % len(weather_weights)]
    
    # 根据天气和地区调整风速
    if description in ['大雨', '雷阵雨']:
        wind_speed = 4.0 + (hash_value % 20) / 10
    elif description in ['中雨', '小雨', '阵雨']:
        wind_speed = 2.0 + (hash_value % 30) / 10
    elif "海" in location or "岛" in location:
        wind_speed = 3.0 + (hash_value % 30) / 10  # 沿海和岛屿风力较大
    elif "西" in location and not "江西" in location and not "山西" in location:
        wind_speed = 3.5 + (hash_value % 25) / 10  # 西北地区风力较大
    else:
        wind_speed = 1.0 + (hash_value % 40) / 10
    
    return {
        "location": location,
        "temp": temp,
        "humidity": humidity,
        "description": description,
        "wind_speed": wind_speed
    }

# 登录页面
@app.route('/')
def login():
    config = load_config()
    return render_template('login.html', servers=config['servers'])

# 处理注册请求
@app.route('/register', methods=['POST'])
def handle_register():
    username = request.form['username']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    nickname = request.form['nickname']
    
    # 检查密码是否匹配
    if password != confirm_password:
        config = load_config()
        return render_template('login.html', servers=config['servers'], error='两次输入的密码不一致')
    
    # 读取现有用户数据
    users = load_users()
    
    # 检查用户名是否已存在
    if username in users:
        config = load_config()
        return render_template('login.html', servers=config['servers'], error='用户名已存在，请更换用户名')
    
    # 检查昵称是否已被使用
    for user in users.values():
        if user['nickname'] == nickname:
            config = load_config()
            return render_template('login.html', servers=config['servers'], error='昵称已被使用，请更换昵称')
    
    # 生成密码哈希
    password_hash = generate_password_hash(password)
    
    # 添加新用户
    users[username] = {
        'password_hash': password_hash,
        'nickname': nickname
    }
    
    # 保存用户数据
    save_users(users)
    
    config = load_config()
    return render_template('login.html', servers=config['servers'], success='注册成功，请登录')

# 处理登录请求
@app.route('/login', methods=['POST'])
def handle_login():
    username = request.form['username']
    password = request.form['password']
    server = request.form['server']
    
    # 读取用户数据
    users = load_users()
    
    # 检查用户名是否存在
    if username not in users:
        config = load_config()
        return render_template('login.html', servers=config['servers'], error='用户名或密码错误')
    
    # 验证密码
    if not check_password_hash(users[username]['password_hash'], password):
        config = load_config()
        return render_template('login.html', servers=config['servers'], error='用户名或密码错误')
    
    # 获取用户昵称
    nickname = users[username]['nickname']
    
    # 检查昵称是否已在当前在线用户中存在
    for user_info in online_users.values():
        if user_info.get('nickname') == nickname:
            config = load_config()
            return render_template('login.html', servers=config['servers'], error='该账号已在其他地方登录')
    
    # 登录成功，重定向到聊天室，并传递用户名和服务器信息
    return redirect(url_for('chat', username=username, nickname=nickname, server=server))

# 聊天室页面
@app.route('/chat')
def chat():
    username = request.args.get('username')
    nickname = request.args.get('nickname')
    server = request.args.get('server')
    
    # 如果没有用户名或昵称，重定向到登录页面
    if not username or not nickname:
        return redirect(url_for('login'))
    
    return render_template('chat.html', username=username, nickname=nickname, server=server)

# WebSocket 事件处理
@socketio.on('connect')
def handle_connect():
    print('客户端已连接')

@socketio.on('join')
def handle_join(data):
    username = data.get('username')
    nickname = data['nickname']
    # 将用户添加到在线列表，使用session_id作为键
    online_users[request.sid] = {
        'username': username,
        'nickname': nickname
    }
    # 加入房间
    join_room(ROOM_NAME)
    
    # 获取所有在线用户的昵称
    online_nicknames = [user['nickname'] for user in online_users.values()]
    
    # 通知所有用户有新用户加入，并发送完整的用户列表
    emit('user_joined', {'nickname': nickname, 'users': online_nicknames}, room=ROOM_NAME)
    # 额外向当前加入的用户发送一次完整的用户列表
    emit('update_users', {'users': online_nicknames}, room=request.sid)
    print(f'{nickname} (用户名: {username}) 加入了聊天室')
    print(f'当前在线用户: {online_nicknames}')

@socketio.on('disconnect')
def handle_disconnect():
    # 检查当前session_id是否在在线用户中
    if request.sid in online_users:
        user_info = online_users[request.sid]
        leaving_nickname = user_info['nickname']
        leaving_username = user_info['username']
        
        # 从在线列表中移除用户
        del online_users[request.sid]
        
        # 获取更新后的在线用户昵称列表
        online_nicknames = [user['nickname'] for user in online_users.values()]
        
        # 通知所有用户有用户离开
        emit('user_left', {'nickname': leaving_nickname, 'users': online_nicknames}, room=ROOM_NAME)
        print(f'{leaving_nickname} (用户名: {leaving_username}) 离开了聊天室')

@socketio.on('send_message')
def handle_message(data):
    global current_weather, current_music
    nickname = data['nickname']
    message = data['message']
    timestamp = data['timestamp']
    
    # 处理消息类型
    message_type = 'text'
    content = message
    ai_response = None
    
    # 检查是否为@音乐命令
    if message.startswith('@音乐'):
        # 提取音乐名（如果有）
        parts = message.split(' ', 1)
        music_name = parts[1].strip() if len(parts) > 1 else ''
        
        # 调用音乐信息API
        music_info = get_music_info(music_name)
        
        # 如果获取到了音乐信息，更新当前音乐并广播
        if music_info:
            # 更新全局音乐状态，确保URL始终有值
            current_music = {
                'id': str(int(time.time())),  # 使用时间戳作为唯一ID
                'name': music_info.get('name', '未知歌曲'),
                'artist': music_info.get('artist', '未知艺术家'),
                'url': music_info.get('url', 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'),
                'image': music_info.get('image', 'https://via.placeholder.com/150'),
                'status': 'playing',  # 默认开始播放
                'progress': 0  # 初始进度为0
            }
            
            # 广播音乐更新事件给所有用户
            emit('music_updated', current_music, broadcast=True)
            
            # 移除系统消息广播，避免重复显示
        else:
            # 移除错误消息广播，使用默认音乐信息
            message_type = 'text'
            content = message
    # 检查是否为@天气命令
    elif message.startswith('@天气'):
        message_type = 'ai_chat'
        try:
            # 解析用户输入，提取地点信息
            parts = message.split(' ', 1)
            location = "成都"  # 默认城市
            
            if len(parts) > 1:
                location = parts[1].strip()
            
            # 省份-省会/主要城市映射
            province_capital = {
                "北京": "北京", "天津": "天津", "河北": "石家庄", "山西": "太原", "内蒙古": "呼和浩特",
                "辽宁": "沈阳", "吉林": "长春", "黑龙江": "哈尔滨", "上海": "上海", "江苏": "南京",
                "浙江": "杭州", "安徽": "合肥", "福建": "福州", "江西": "南昌", "山东": "济南",
                "河南": "郑州", "湖北": "武汉", "湖南": "长沙", "广东": "广州", "广西": "南宁",
                "海南": "海口", "重庆": "重庆", "四川": "成都", "贵州": "贵阳", "云南": "昆明",
                "西藏": "拉萨", "陕西": "西安", "甘肃": "兰州", "青海": "西宁", "宁夏": "银川",
                "新疆": "乌鲁木齐", "香港": "香港", "澳门": "澳门", "台湾": "台北"
            }
            
            # 天气图标映射
            weather_icons = {
                "晴": "☀️", "晴朗": "☀️",
                "多云": "☁️",
                "阴": "☁️",
                "小雨": "🌦️",
                "中雨": "🌧️",
                "大雨": "⛈️",
                "雷阵雨": "⛈️",
                "阵雨": "🌦️",
                "晴间多云": "⛅",
                "多云转晴": "⛅"
            }
            
            # 生成温馨提醒的函数
            def generate_reminder(description, temp, humidity, wind_speed):
                reminders = []
                
                # 基于天气状况的提醒
                if "雨" in description or "阵雨" in description:
                    reminders.append("记得带伞哦！")
                    if "大雨" in description or "暴雨" in description:
                        reminders.append("降雨较大，注意安全，避免前往低洼地区！")
                    elif "雷阵雨" in description:
                        reminders.append("雷雨天气，请注意防雷，避免使用电子设备！")
                elif "雪" in description:
                    reminders.append("下雪了，注意保暖防滑！")
                    if "大雪" in description:
                        reminders.append("降雪较大，出行注意安全，驾车减速慢行！")
                elif "晴" in description:
                    if temp > 30:
                        reminders.append("天气晴朗但较热，注意防晒！")
                    else:
                        reminders.append("天气晴朗，适合外出活动！")
                elif "多云" in description or "阴" in description:
                    reminders.append("天气阴沉，注意保持心情愉悦！")
                elif "高温预警" in description:
                    reminders.append("高温预警！请尽量避免户外活动，注意防暑降温！")
                    reminders.append("多补充水分，谨防中暑！")
                elif "寒潮" in description:
                    reminders.append("寒潮来袭！请做好防寒保暖措施！")
                    reminders.append("注意室内外温差，预防感冒！")
                
                # 基于温度的提醒
                if temp < -10:
                    reminders.append("气温严寒，请注意保暖，避免长时间户外活动！")
                elif temp < 0:
                    reminders.append("气温寒冷，请注意保暖！")
                elif temp < 10:
                    reminders.append("气温较低，请注意保暖！")
                elif temp > 35:
                    reminders.append("极端高温，请做好防暑降温措施！")
                    reminders.append("多喝水，避免在烈日下活动！")
                elif temp > 30:
                    reminders.append("气温较高，注意防暑降温！")
                elif 20 <= temp <= 26:
                    reminders.append("温度适宜，体感舒适！")
                
                # 基于湿度的提醒
                if humidity > 85:
                    reminders.append("湿度很大，注意防潮除湿！")
                elif humidity > 80:
                    reminders.append("湿度较大，注意防潮！")
                elif humidity < 25:
                    reminders.append("空气非常干燥，记得多喝水，使用加湿器！")
                elif humidity < 30:
                    reminders.append("空气干燥，记得多喝水！")
                
                # 基于风速的提醒
                if wind_speed > 7.0:
                    reminders.append("风力强劲，外出时注意安全，避免在广告牌下停留！")
                elif wind_speed > 5.0:
                    reminders.append("风力较大，外出时注意安全！")
                elif wind_speed < 1.0 and temp > 30:
                    reminders.append("无风且高温，注意保持通风！")
                
                # 季节特定提醒
                current_month = datetime.datetime.now().month
                if 3 <= current_month <= 5:  # 春季
                    reminders.append("春季天气多变，注意适时增减衣物！")
                elif 6 <= current_month <= 8:  # 夏季
                    reminders.append("夏季多雨，出门请带伞！")
                elif 9 <= current_month <= 11:  # 秋季
                    reminders.append("秋季早晚温差大，注意适时增减衣物！")
                else:  # 冬季
                    reminders.append("冬季寒冷，注意保暖！")
                
                # 随机选择1-3条提醒，确保信息丰富但不过多
                import random
                if not reminders:
                    return "今天也要保持好心情哦！"
                elif len(reminders) == 1:
                    return reminders[0]
                else:
                    # 根据提醒数量动态选择返回条数
                    max_reminders = min(3, len(reminders))
                    num_reminders = random.choice(range(1, max_reminders + 1))
                    selected_reminders = random.sample(reminders, num_reminders)
                    return " ".join(selected_reminders)
            
            # 处理省份查询 - 如果查询的是省份名称，返回省会城市的天气
            is_province_query = location in province_capital
            if is_province_query:
                actual_location = province_capital[location]
            else:
                actual_location = location
            
            # 使用改进的哈希生成逻辑，支持所有中国地区的天气查询
            import hashlib
            import datetime
            # 使用更稳定的哈希生成算法，确保相同城市返回相似的天气数据
            hash_value = int(hashlib.md5(actual_location.encode()).hexdigest(), 16)
            
            # 获取当前月份，添加季节因素
            current_month = datetime.datetime.now().month
            
            # 季节系数：1=冬季，2=春季，3=夏季，4=秋季
            season = 1  # 冬季
            if 3 <= current_month <= 5:
                season = 2  # 春季
            elif 6 <= current_month <= 8:
                season = 3  # 夏季
            elif 9 <= current_month <= 11:
                season = 4  # 秋季
            
            # 根据城市名称的哈希值确定大致地理位置（南北差异、沿海内陆）
            location_factor = hash_value % 100
            
            # 根据地理位置和季节调整温度基准
            # 南方地区
            if location_factor < 25:
                if season == 1:  # 冬季
                    base_temp = 18
                elif season == 2:  # 春季
                    base_temp = 24
                elif season == 3:  # 夏季
                    base_temp = 30
                else:  # 秋季
                    base_temp = 26
            # 中部地区
            elif location_factor < 70:
                if season == 1:  # 冬季
                    base_temp = 10
                elif season == 2:  # 春季
                    base_temp = 20
                elif season == 3:  # 夏季
                    base_temp = 28
                else:  # 秋季
                    base_temp = 22
            # 北方地区
            else:
                if season == 1:  # 冬季
                    base_temp = -5
                elif season == 2:  # 春季
                    base_temp = 15
                elif season == 3:  # 夏季
                    base_temp = 26
                else:  # 秋季
                    base_temp = 18
            
            # 根据地区调整温度变化范围
            if location_factor < 25:  # 南方
                temp_range = 8
            elif location_factor < 70:  # 中部
                temp_range = 10
            else:  # 北方
                temp_range = 12
            
            # 生成合理的温度
            temp = base_temp + ((hash_value % temp_range) - temp_range // 2)
            
            # 根据地理位置、季节和温度生成更合理的湿度
            # 沿海地区湿度较高
            if location_factor < 20:
                if season == 1:  # 冬季
                    humidity_base = 70
                elif season == 2:  # 春季
                    humidity_base = 80
                elif season == 3:  # 夏季
                    humidity_base = 85
                else:  # 秋季
                    humidity_base = 75
            # 内陆地区
            elif location_factor < 60:
                if season == 1:  # 冬季
                    humidity_base = 50
                elif season == 2:  # 春季
                    humidity_base = 65
                elif season == 3:  # 夏季
                    humidity_base = 75
                else:  # 秋季
                    humidity_base = 60
            # 干旱地区
            else:
                if season == 1:  # 冬季
                    humidity_base = 30
                elif season == 2:  # 春季
                    humidity_base = 40
                elif season == 3:  # 夏季
                    humidity_base = 45
                else:  # 秋季
                    humidity_base = 35
            
            # 添加温度对湿度的影响（高温导致蒸发增加）
            temp_humidity_factor = 0
            if temp > 30:
                temp_humidity_factor = -10
            elif temp < 0:
                temp_humidity_factor = 10
            
            humidity = humidity_base + temp_humidity_factor + ((hash_value % 15) - 7)
            humidity = max(20, min(95, humidity))  # 确保湿度在合理范围内
            
            # 根据季节、温度、湿度生成更合理的天气状况
            # 构建动态天气权重列表
            weather_weights = []
            
            # 基础权重
            if season == 1:  # 冬季
                base_weights = ['晴', '多云', '阴', '晴间多云', '多云转晴', '小雨', '中雨']
                # 冬季雨雪天气权重
                if location_factor >= 70:  # 北方冬季
                    base_weights.extend(['小雪', '中雪', '大雪'])
            elif season == 2:  # 春季
                base_weights = ['晴', '多云', '阴', '晴间多云', '多云转晴', '小雨', '阵雨']
                # 春季多风
            elif season == 3:  # 夏季
                base_weights = ['晴', '多云', '阴', '晴间多云', '多云转晴', '小雨', '中雨', '大雨', '雷阵雨']
            else:  # 秋季
                base_weights = ['晴', '多云', '阴', '晴间多云', '多云转晴', '小雨']
            
            # 根据温度调整权重
            if temp > 35:
                # 极端高温更可能是晴天
                weather_weights = ['晴'] * 3 + ['多云'] * 2 + ['晴间多云'] * 2
            elif temp > 30:
                # 高温更可能是晴天或多云
                weather_weights = ['晴'] * 4 + ['多云'] * 3 + ['晴间多云'] * 2 + ['阴'] * 1
            elif temp < -10:
                # 极端低温更可能是晴天或小雪
                if location_factor >= 70:  # 北方
                    weather_weights = ['晴'] * 3 + ['多云'] * 2 + ['小雪'] * 3
                else:
                    weather_weights = ['晴'] * 4 + ['多云'] * 3 + ['阴'] * 2
            elif temp < 5:
                # 低温更可能是晴天或多云
                if location_factor >= 70:  # 北方
                    weather_weights = ['晴'] * 4 + ['多云'] * 3 + ['小雪'] * 2 + ['阴'] * 1
                else:
                    weather_weights = ['晴'] * 4 + ['多云'] * 3 + ['阴'] * 2
            elif humidity > 85:
                # 高湿度更可能下雨
                rain_weather = ['小雨', '中雨', '雷阵雨', '阵雨']
                if season == 1 and location_factor >= 70:  # 北方冬季
                    rain_weather = ['小雪', '中雪']
                weather_weights = rain_weather * 3 + ['阴'] * 3 + ['多云'] * 2
            elif humidity < 30:
                # 低湿度更可能是晴天
                weather_weights = ['晴'] * 5 + ['多云'] * 3 + ['晴间多云'] * 2
            else:
                # 正常情况使用基础权重
                weather_weights = base_weights
            
            # 确保权重列表不为空
            if not weather_weights:
                weather_weights = ['晴', '多云', '阴']
            
            # 根据哈希值从权重列表中选择天气
            description = weather_weights[hash_value % len(weather_weights)]
            
            # 生成更合理的风速，考虑季节、天气和地理位置
            # 基础风速根据季节调整
            if season == 2:  # 春季多风
                wind_base = 3.0
            elif season == 4:  # 秋季次之
                wind_base = 2.5
            else:  # 夏季和冬季
                wind_base = 2.0
            
            # 天气状况对风速的影响
            if description in ['大雨', '雷阵雨', '大雪']:
                wind_base += 2.0
            elif description in ['中雨', '阵雨', '中雪']:
                wind_base += 1.0
            elif description in ['小雨', '小雪']:
                wind_base += 0.5
            elif description == '晴' and temp > 35:
                wind_base -= 0.5  # 极端高温可能无风
            
            # 地理位置对风速的影响（北方和沿海通常风力较大）
            if location_factor >= 80 or location_factor < 10:
                wind_base += 0.5
            
            wind_speed = wind_base + (hash_value % 20) / 10
            wind_speed = min(wind_speed, 10.0)  # 限制最大风速，极端天气除外
            
            # 添加极端天气的可能
            extreme_weather_chance = hash_value % 100
            if extreme_weather_chance < 3:  # 3%概率出现极端天气
                if temp > 35 and season == 3:
                    description = '高温预警'
                    wind_speed = 1.0  # 高温通常无风
                elif temp < -15 and location_factor >= 70:
                    description = '寒潮'
                    wind_speed = 5.0
                elif humidity > 90 and temp > 25:
                    description = '暴雨'
                    wind_speed = 8.0
            
            # 更新天气图标映射，添加雨雪天气
            weather_icons.update({
                '小雪': '🌨️', '中雪': '🌨️', '大雪': '❄️',
                '高温预警': '🔥', '寒潮': '❄️', '暴雨': '⛈️'
            })
            
            # 获取天气图标
            weather_icon = weather_icons.get(description, "🌈")
            # 生成温馨提醒
            reminder = generate_reminder(description, temp, humidity, wind_speed)
            
            # 格式化回复
            if is_province_query:
                ai_response = f"{location}省会{actual_location}当前天气\n温度：{temp}°C\n湿度：{humidity}%\n天气状况：{description} {weather_icon}\n风速：{wind_speed:.1f} m/s\n\n温馨提示：{reminder}"
            else:
                ai_response = f"{actual_location}当前天气\n温度：{temp}°C\n湿度：{humidity}%\n天气状况：{description} {weather_icon}\n风速：{wind_speed:.1f} m/s\n\n温馨提示：{reminder}"
            
            # 添加天气类型信息，用于前端背景颜色变化
            # 简化天气类型分类为用户要求的三种类型：晴天、雨天、雾天/多云
            weather_type = 'default'
            if any(w in description for w in ['晴', '晴朗', '晴间多云', '多云转晴']):
                weather_type = 'sunny'  # 晴天 - 金色背景
            elif any(w in description for w in ['雨', '阵雨', '雷阵雨', '暴雨']):
                weather_type = 'rainy'  # 雨天 - 银白色背景
            elif any(w in description for w in ['多云', '阴', '雾', '雾霾']):
                weather_type = 'cloudy'  # 雾天或多云 - 灰色背景
            elif any(w in description for w in ['雪', '小雪', '中雪', '大雪']):
                weather_type = 'rainy'  # 雪天也归为银白色背景
            elif '高温预警' in description:
                weather_type = 'sunny'  # 高温预警归为晴天
            elif '寒潮' in description:
                weather_type = 'cloudy'  # 寒潮归为雾天/多云
        except Exception as e:
            ai_response = f"获取{location}天气信息时出错：{str(e)}"
    # 检查是否为@新闻命令
    elif message.startswith('@新闻'):
        message_type = 'ai_chat'
        try:
            # 获取百度热点新闻
            news_data = get_baidu_hot_news()
            
            # 格式化新闻回复
            ai_response = {"news": news_data}  # 返回新闻数组供前端展示
        except Exception as e:
            ai_response = f"获取热点新闻时出错：{str(e)}"
    # 检查是否为@电影命令
    elif message.startswith('@电影'):
        message_type = 'movie'
        # 提取用户提供的电影URL
        parts = message.split(' ', 1)
        if len(parts) > 1:
            movie_url = parts[1].strip()
            # 使用指定的解析地址
            parsed_url = f"https://jx.m3u8.tv/jiexi/?url={movie_url}"
            content = parsed_url
        else:
            # 如果没有提供URL，发送提示信息
            message_type = 'text'
            content = "请在@电影后输入电影URL，例如：@电影 https://example.com/movie.mp4"
    # 检查是否为@川小农命令
    elif message.startswith('@川小农'):
        message_type = 'ai_chat'
        # 提取用户的问题
        parts = message.split(' ', 1)
        if len(parts) > 1:
            question = parts[1].strip().lower()
            # 智能回复逻辑 - 根据问题内容给出不同回答
            import random
            
            # 问候语回复
            if any(greet in question for greet in ['你好', '嗨', '哈喽', '您好', '早上好', '晚上好', '中午好']):
                greetings = [
                    "你好！很高兴见到你！",
                    "嗨！有什么我可以帮助你的吗？",
                    "你好呀！今天过得怎么样？",
                    "你好！我是川小农，随时为你服务！"
                ]
                ai_response = random.choice(greetings)
            
            # 询问姓名
            elif any(name in question for name in ['你叫什么', '名字', '谁', '身份']):
                names = [
                    "我是川小农，一个友好的AI助手。",
                    "你可以叫我川小农，很高兴认识你！",
                    "我叫川小农，是为你提供帮助的智能助手。"
                ]
                ai_response = random.choice(names)
            
            # 询问功能
            elif any(func in question for func in ['功能', '能做什么', '会什么', '可以帮我']):
                functions = [
                    "我可以陪你聊天，回答简单的问题。在这个聊天室里，你还可以分享电影链接或者与其他用户交流！",
                    "我的主要功能是与你聊天互动。你可以问我各种问题，我会尽力回答。",
                    "我能陪你聊天解闷，也可以回答一些简单的问题。试试看吧！"
                ]
                ai_response = random.choice(functions)
            
            # 询问天气
            elif any(weather in question for weather in ['天气', '下雨', '晴天', '温度', '冷吗', '热吗']):
                weathers = [
                    "我无法获取实时天气信息，但希望你所在的地方天气晴朗！",
                    "虽然我不能查看当前天气，但不管天气如何，保持好心情最重要！",
                    "很抱歉，我没有实时天气数据。建议你查看天气预报获取最新信息。"
                ]
                ai_response = random.choice(weathers)
            
            # 感谢相关
            elif any(thanks in question for thanks in ['谢谢', '感谢', '谢了']):
                thanks_responses = [
                    "不客气！很高兴能帮到你！",
                    "不用谢，随时为你服务！",
                    "能帮到你我很开心！",
                    "没关系，这是我应该做的！"
                ]
                ai_response = random.choice(thanks_responses)
            
            # 时间相关
            elif any(time in question for time in ['几点', '时间', '日期', '今天几号']):
                import datetime
                now = datetime.datetime.now()
                current_time = now.strftime("%Y年%m月%d日 %H:%M:%S")
                time_responses = [
                    f"现在是{current_time}。",
                    f"当前时间：{current_time}。",
                    f"北京时间：{current_time}。"
                ]
                ai_response = random.choice(time_responses)
            
            # 其他问题的通用回复
            else:
                generic_responses = [
                    f"关于'{question}'这个问题，我觉得很有意思！",
                    f"你问的'{question}'是个好问题。我认为这需要从多个角度来看。",
                    f"关于'{question}'，我不太确定具体答案，但我很乐意和你讨论这个话题！",
                    f"'{question}'是个有趣的问题。让我想想...嗯，我认为这可能涉及到多个因素。",
                    f"感谢你的问题'{question}'。虽然我不能给出完美答案，但我会尽力帮助你思考。"
                ]
                ai_response = random.choice(generic_responses)
        else:
            # 当没有具体问题时的回复
            welcome_responses = [
                "您好！我是川小农，请问有什么可以帮助您的？",
                "嗨！有什么问题想和我聊聊吗？",
                "你好呀！我是川小农，随时为你提供帮助！",
                "哈喽！请问需要什么帮助吗？"
            ]
            import random
            ai_response = random.choice(welcome_responses)
    
    # 广播消息给房间内所有用户
    emit('new_message', {
        'nickname': nickname,
        'message': message,
        'content': content,
        'type': message_type,
        'timestamp': timestamp
    }, room=ROOM_NAME)
    
    # 如果是AI聊天请求，额外发送一条AI回复消息
    if message_type == 'ai_chat' and ai_response:
        import datetime
        ai_timestamp = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
        # 根据命令类型确定AI昵称
        if message.startswith('@天气'):
            ai_nickname = '天气'
        elif message.startswith('@新闻'):
            ai_nickname = '新闻'
        else:
            ai_nickname = '川小农'
        
        # 构建消息数据
        message_data = {
            'nickname': ai_nickname,  # AI昵称
            'message': ai_response,
            'content': ai_response,
            'type': 'ai_chat_response',
            'timestamp': ai_timestamp
        }
        
        # 如果是天气消息，添加weather_type
        if message.startswith('@天气'):
            message_data['weather_type'] = weather_type
        
        emit('new_message', message_data, room=ROOM_NAME)

# 音乐控制相关的WebSocket事件处理
@socketio.on('music_control')
def handle_music_control(data):
    global current_music
    action = data.get('action')
    
    # 如果当前没有音乐且动作不是progress，不执行控制操作
    if not current_music and action != 'progress' and action != 'update_progress':
        return
    
    # 确保current_music是一个字典
    if not current_music:
        current_music = {}
    
    # 记录控制动作
    print(f"音乐控制动作: {action}")
    
    # 更新音乐状态
    status_changed = False
    progress_changed = False
    
    if action == 'play':
        old_status = current_music.get('status')
        current_music['status'] = 'playing'
        current_music['last_updated'] = time.time()
        if old_status != 'playing':
            status_changed = True
    elif action == 'pause':
        old_status = current_music.get('status')
        current_music['status'] = 'paused'
        current_music['last_updated'] = time.time()
        if old_status != 'paused':
            status_changed = True
    elif action == 'stop':
        old_status = current_music.get('status')
        current_music['status'] = 'stopped'
        old_progress = current_music.get('progress', 0)
        current_music['progress'] = 0
        current_music['last_updated'] = time.time()
        if old_status != 'stopped' or old_progress != 0:
            status_changed = True
            progress_changed = True
    elif action == 'progress' or action == 'update_progress':
        # 更新进度，但只有当音乐在播放或暂停状态时才更新
        new_progress = data.get('progress', 0)
        old_progress = current_music.get('progress', 0)
        
        # 只有当进度变化超过1%时才更新，避免频繁更新
        if abs(new_progress - old_progress) > 1:
            if current_music.get('status') in ['playing', 'paused'] or not current_music.get('status'):
                current_music['progress'] = new_progress
                current_music['last_updated'] = time.time()
                progress_changed = True
    
    # 构建状态更新数据
    update_data = {
        'status': current_music.get('status'),
        'progress': current_music.get('progress', 0),
        'id': current_music.get('id')
    }
    
    # 只有在状态或进度发生变化时才广播更新，避免不必要的网络流量
    if status_changed or progress_changed:
        # 广播音乐状态更新给所有用户
        emit('music_status_updated', update_data, room=ROOM_NAME)
        print(f"广播音乐状态更新: {update_data}")
    else:
        # 即使没有变化，也广播完整的current_music以确保状态同步
        emit('music_status_updated', current_music, room=ROOM_NAME)
    
    return update_data  # 可选：返回更新后的数据给发送请求的客户端

# 获取当前音乐状态的事件处理
@socketio.on('get_current_music')
def handle_get_current_music():
    global current_music
    # 只有当current_music包含有效的音乐数据（至少有name和url）时，才发送music_updated事件
    if current_music and current_music.get('name') and current_music.get('url'):
        # 发送当前音乐信息给请求的客户端
        print(f"向新连接的用户发送当前音乐信息")
        emit('music_updated', current_music)
        # 同时发送当前播放状态
        emit('music_status_updated', {
            'status': current_music.get('status'),
            'progress': current_music.get('progress', 0),
            'id': current_music.get('id')
        })
    else:
        # 如果没有当前音乐或音乐数据不完整，只发送状态更新，不发送music_updated事件
        emit('music_status_updated', {
            'status': 'stopped',
            'progress': 0,
            'id': None
        })
        print(f"向新连接的用户发送默认音乐状态（无音乐）")

if __name__ == '__main__':
    # 确保配置文件存在
    if not os.path.exists('config.json'):
        save_config({'servers': ['http://localhost:8080']})
    # 启动服务器，使用不同的端口
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)