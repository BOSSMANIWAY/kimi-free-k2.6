#!/usr/bin/env python3
"""Kimi API client - Using curl for HTTP/2 streaming"""
import json
import struct
import sys
import os
import subprocess
import tempfile

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kimi_token.txt')
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kimi_state.json')

SCENARIOS = {
    'k2d5': 'SCENARIO_K2D5',
    'computer': 'SCENARIO_OK_COMPUTER',
}

def get_token():
    with open(TOKEN_FILE, 'r') as f:
        return f.read().strip()

def get_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def make_connect_frame(json_obj):
    json_str = json.dumps(json_obj, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    length = len(json_bytes)
    return bytes([0x00]) + struct.pack('>I', length) + json_bytes

def send_message(message, scenario='k2d5', thinking=True, enable_plugin=True, reasoning_effort='LOW'):
    TOKEN = get_token()
    state = get_state()
    
    chat_id = state.get('chat_id', '')
    parent_id = state.get('parent_id', '')
    
    scenario_name = SCENARIOS.get(scenario, 'SCENARIO_K2D5')
    
    tools = []
    if scenario == 'computer':
        tools = [
            {"type": "TOOL_TYPE_SEARCH", "search": {}},
            {"type": "TOOL_TYPE_CRON_JOB"}
        ]
    
    body = {
        "chat_id": chat_id,
        "scenario": scenario_name,
        "tools": tools,
        "message": {
            "parent_id": parent_id,
            "role": "user",
            "blocks": [{"message_id": "", "text": {"content": message}}],
            "scenario": scenario_name,
            "is_goal": False
        },
        "options": {
            "thinking": thinking,
            "enable_plugin": enable_plugin,
            "reasoning_effort": f"REASONING_EFFORT_{reasoning_effort.upper()}"
        },
        "project_id": ""
    }
    
    request_frame = make_connect_frame(body)
    
    # Write request to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
        f.write(request_frame)
        req_file = f.name
    
    headers = [
        f'-H', f'accept: */*',
        f'-H', f'authorization: Bearer {TOKEN}',
        f'-H', f'cache-control: no-cache',
        f'-H', f'connect-protocol-version: 1',
        f'-H', f'content-type: application/connect+json',
        f'-H', f'origin: https://www.kimi.com',
        f'-H', f'pragma: no-cache',
        f'-H', f'priority: u=1, i',
        f'-H', f'r-timezone: Europe/Moscow',
        f'-H', f'referer: https://www.kimi.com/chat/{chat_id}' if chat_id else f'-H', f'referer: https://www.kimi.com/chat',
        f'-H', f'sec-ch-ua: Not;A=Brand;v=8, Chromium;v=150, Google Chrome;v=150',
        f'-H', f'sec-ch-ua-mobile: ?0',
        f'-H', f'sec-ch-ua-platform: macOS',
        f'-H', f'sec-fetch-dest: empty',
        f'-H', f'sec-fetch-mode: cors',
        f'-H', f'sec-fetch-site: same-origin',
        f'-H', f'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
        f'-H', f'x-language: en-US',
        f'-H', f'x-msh-device-id: 7646412723261079043',
        f'-H', f'x-msh-platform: web',
        f'-H', f'x-msh-session-id: 1731724216701107694',
        f'-H', f'x-msh-shield-data: sg:fk4BhWf9xSf8wCffEujQZwoz7Z',
        f'-H', f'x-msh-version: 2.0.0',
        f'-H', f'x-traffic-id: d92gbpsqdqejco9rrso0',
    ]
    
    display = f"{message[:100]}..." if len(message) > 100 else message
    print(f'User: {display}')
    print(f'Scenario: {scenario_name} | Thinking: {thinking} | Plugin: {enable_plugin} | Effort: {reasoning_effort}')
    print()
    
    full_text = ""
    frame_count = 0
    done_received = False
    idle_count = 0
    max_idle = 10
    
    try:
        cmd = ['curl', '--http2', '-s', '-N', '-X', 'POST',
               'https://www.kimi.com/apiv2/kimi.gateway.chat.v1.ChatService/Chat',
               '--data-binary', f'@{req_file}'] + headers
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Set a timeout on the stdout file descriptor using select
        import select
        
        buf = b''
        
        while True:
            # Exit if process ended and buffer is drained
            if proc.poll() is not None and not buf:
                break
            
            # Use select with timeout to avoid blocking forever
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            
            if not ready:
                # No data for 1 second
                if done_received:
                    # Got done signal, wait a bit more for final frames then exit
                    idle_count += 1
                    if idle_count >= 3:
                        break
                else:
                    idle_count += 1
                    if idle_count >= max_idle:
                        print('\n[Server stopped responding]')
                        proc.terminate()
                        break
                continue
            
            idle_count = 0
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            
            buf += chunk
            
            while len(buf) >= 5:
                flags = buf[0]
                resp_length = int.from_bytes(buf[1:5], 'big')
                
                if len(buf) < 5 + resp_length:
                    break
                
                frame_body = buf[5:5+resp_length]
                buf = buf[5+resp_length:]
                frame_count += 1
                
                try:
                    decoded = frame_body.decode('utf-8')
                    parsed = json.loads(decoded)
                    
                    if 'chat' in parsed and 'id' in parsed['chat']:
                        state['chat_id'] = parsed['chat']['id']
                    
                    if 'message' in parsed and 'id' in parsed['message']:
                        state['parent_id'] = parsed['message']['id']
                    
                    if 'op' in parsed and parsed['op'] == 'append' and 'block' in parsed:
                        text = parsed['block'].get('text', {}).get('content', '')
                        full_text += text
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    
                    elif 'op' in parsed and parsed['op'] == 'set' and 'block' in parsed:
                        text = parsed['block'].get('text', {}).get('content', '')
                        full_text = text
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    
                    elif 'done' in parsed:
                        done_received = True
                        print('\n')
                
                except:
                    pass

    except Exception as e:
        print(f'\n[Error: {e}]')
    finally:
        os.unlink(req_file)
    
    save_state(state)
    print(f'\n=== Total frames: {frame_count} ===')
    if state.get('chat_id'):
        print(f'Chat ID: {state["chat_id"]}')

if __name__ == '__main__':
    args = sys.argv[1:]
    
    scenario = 'k2d5'
    thinking = True
    enable_plugin = True
    reasoning_effort = 'LOW'
    file_path = None
    
    if '--computer' in args:
        scenario = 'computer'
        args.remove('--computer')
    
    if '--no-thinking' in args:
        thinking = False
        args.remove('--no-thinking')
    
    if '--no-plugin' in args:
        enable_plugin = False
        args.remove('--no-plugin')
    
    if '--effort-low' in args:
        reasoning_effort = 'LOW'
        args.remove('--effort-low')
    elif '--effort-medium' in args:
        reasoning_effort = 'MEDIUM'
        args.remove('--effort-medium')
    elif '--effort-high' in args:
        reasoning_effort = 'HIGH'
        args.remove('--effort-high')
    
    if '--new' in args:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print('Chat reset. Starting new conversation.\n')
        args.remove('--new')
    
    if '--file' in args:
        idx = args.index('--file')
        if idx + 1 < len(args):
            file_path = args[idx + 1]
            args = args[:idx] + args[idx+2:]
        else:
            print('Error: --file requires a path argument')
            sys.exit(1)
    
    message = ' '.join(args) if args else "Hello, how are you?"
    
    if file_path:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            message = f"{message}\n\nFile content ({file_path}):\n{content}"
        except Exception as e:
            print(f'Error reading file: {e}')
            sys.exit(1)
    
    send_message(message, scenario, thinking, enable_plugin, reasoning_effort)
