#!/usr/bin/env python3
"""Kimi Chat CLI — единый клиент для Kimi AI API (Connect Protocol over HTTP/2)"""

# ─── CONFIG ──────────────────────────────────────────────────────────
# Укажите ваш JWT-токен (получить в настройках Kimi → DevTools → Network):
TOKEN = ""
# ─────────────────────────────────────────────────────────────────────

import json, struct, sys, os, subprocess, tempfile, select

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kimi_state.json')
SCENARIOS = {'k2d5': 'SCENARIO_K2D5', 'computer': 'SCENARIO_OK_COMPUTER'}


def get_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def make_connect_frame(obj):
    data = json.dumps(obj, separators=(',', ':')).encode('utf-8')
    return b'\x00' + struct.pack('>I', len(data)) + data


def send_message(message, scenario='k2d5', thinking=True, enable_plugin=True, effort='LOW'):
    state = get_state()
    chat_id = state.get('chat_id', '')
    parent_id = state.get('parent_id', '')
    scenario_name = SCENARIOS.get(scenario, 'SCENARIO_K2D5')

    tools = [{"type": "TOOL_TYPE_SEARCH", "search": {}}, {"type": "TOOL_TYPE_CRON_JOB"}] if scenario == 'computer' else []

    body = {
        "chat_id": chat_id, "scenario": scenario_name, "tools": tools,
        "message": {"parent_id": parent_id, "role": "user",
                     "blocks": [{"message_id": "", "text": {"content": message}}],
                     "scenario": scenario_name, "is_goal": False},
        "options": {"thinking": thinking, "enable_plugin": enable_plugin,
                     "reasoning_effort": f"REASONING_EFFORT_{effort.upper()}"},
        "project_id": ""
    }

    req = make_connect_frame(body)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
        f.write(req)
        req_file = f.name

    ref = f'https://www.kimi.com/chat/{chat_id}' if chat_id else 'https://www.kimi.com/chat'
    headers = [
        '-H', 'accept: */*', '-H', f'authorization: Bearer {TOKEN}',
        '-H', 'cache-control: no-cache', '-H', 'connect-protocol-version: 1',
        '-H', 'content-type: application/connect+json', '-H', 'origin: https://www.kimi.com',
        '-H', 'pragma: no-cache', '-H', 'priority: u=1, i', '-H', 'r-timezone: Europe/Moscow',
        '-H', f'referer: {ref}',
        '-H', 'sec-ch-ua: Not;A=Brand;v=8, Chromium;v=150, Google Chrome;v=150',
        '-H', 'sec-ch-ua-mobile: ?0', '-H', 'sec-ch-ua-platform: macOS',
        '-H', 'sec-fetch-dest: empty', '-H', 'sec-fetch-mode: cors', '-H', 'sec-fetch-site: same-origin',
        '-H', 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        '-H', 'x-language: en-US', '-H', 'x-msh-device-id: 7646412723261079043',
        '-H', 'x-msh-platform: web', '-H', 'x-msh-session-id: 1731724216701107694',
        '-H', 'x-msh-shield-data: sg:fk4BhWf9xSf8wCffEujQZwoz7Z',
        '-H', 'x-msh-version: 2.0.0', '-H', 'x-traffic-id: d92gbpsqdqejco9rrso0',
    ]

    display = f"{message[:100]}..." if len(message) > 100 else message
    print(f'User: {display}')
    print(f'Scenario: {scenario_name} | Thinking: {thinking} | Plugin: {enable_plugin} | Effort: {effort}\n')

    full_text, frame_count, done_received, idle_count = "", 0, False, 0
    try:
        cmd = ['curl', '--http2', '-s', '-N', '-X', 'POST',
               'https://www.kimi.com/apiv2/kimi.gateway.chat.v1.ChatService/Chat',
               '--data-binary', f'@{req_file}'] + headers
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        buf = b''
        while True:
            if proc.poll() is not None and not buf:
                break
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            if not ready:
                idle_count += 1
                if (done_received and idle_count >= 3) or idle_count >= 10:
                    proc.terminate()
                    break
                continue
            idle_count = 0
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            while len(buf) >= 5:
                if len(buf) < 5 + int.from_bytes(buf[1:5], 'big'):
                    break
                resp = buf[5:5 + int.from_bytes(buf[1:5], 'big')]
                buf = buf[5 + int.from_bytes(buf[1:5], 'big'):]
                frame_count += 1
                try:
                    p = json.loads(resp.decode('utf-8'))
                    if 'chat' in p and 'id' in p['chat']:
                        state['chat_id'] = p['chat']['id']
                    if 'message' in p and 'id' in p['message']:
                        state['parent_id'] = p['message']['id']
                    if p.get('op') == 'append' and 'block' in p:
                        t = p['block'].get('text', {}).get('content', '')
                        full_text += t
                        sys.stdout.write(t)
                        sys.stdout.flush()
                    elif p.get('op') == 'set' and 'block' in p:
                        t = p['block'].get('text', {}).get('content', '')
                        full_text = t
                        sys.stdout.write(t)
                        sys.stdout.flush()
                    elif 'done' in p:
                        print('\n')
                except Exception:
                    pass
    except Exception as e:
        print(f'\n[Error: {e}]')
    finally:
        os.unlink(req_file)

    save_state(state)
    print(f'\n=== Frames: {frame_count} ===')
    if state.get('chat_id'):
        print(f'Chat ID: {state["chat_id"]}')


# ─── ARG PARSING ─────────────────────────────────────────────────────
scenario, thinking, enable_plugin, effort = 'k2d5', True, True, 'LOW'
file_path = None

if '--computer' in sys.argv[1:]:
    scenario = 'computer'
    sys.argv.remove('--computer')

if '--no-thinking' in sys.argv[1:]:
    thinking = False
    sys.argv.remove('--no-thinking')

if '--no-plugin' in sys.argv[1:]:
    enable_plugin = False
    sys.argv.remove('--no-plugin')

if '--effort-low' in sys.argv[1:]:
    effort = 'LOW'
    sys.argv.remove('--effort-low')
elif '--effort-medium' in sys.argv[1:]:
    effort = 'MEDIUM'
    sys.argv.remove('--effort-medium')
elif '--effort-high' in sys.argv[1:]:
    effort = 'HIGH'
    sys.argv.remove('--effort-high')

if '--new' in sys.argv[1:]:
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print('Chat reset.\n')
    sys.argv.remove('--new')

if '--file' in sys.argv[1:]:
    idx = sys.argv.index('--file')
    if idx + 1 < len(sys.argv):
        file_path = sys.argv[idx + 1]
        sys.argv = sys.argv[:idx] + sys.argv[idx + 2:]
    else:
        print('Error: --file requires a path')
        sys.exit(1)

message = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello"

if file_path:
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        message = f"{message}\n\nFile ({file_path}):\n{content}"
    except Exception as e:
        print(f'Error reading file: {e}')
        sys.exit(1)

if not TOKEN:
    print("Error: TOKEN is not set. Edit the script and add your JWT token.")
    sys.exit(1)

send_message(message, scenario, thinking, enable_plugin, effort)
