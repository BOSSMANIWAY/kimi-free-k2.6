#!/usr/bin/env python3
"""Kimi Chat CLI — Kimi AI Sandbox Terminal

Kimi = мозг и размышление
Terminal = её руки

Красивый футуристический интерфейс с анимациями и эффектами.
"""

import json, struct, sys, os, subprocess, tempfile, select, re, time, hashlib
from datetime import datetime
from pathlib import Path

# ─── JWT TOKEN ───────────────────────────────────────────────────────
# Токен берется из переменной окружения KIMI_TOKEN для безопасности
TOKEN = os.getenv('KIMI_TOKEN')
if not TOKEN:
    print('\033[91mERROR:\033[0m Token not found. Please set the KIMI_TOKEN environment variable.')
    print('Usage: export KIMI_TOKEN=\'your_jwt_token_here\'')
    sys.exit(1)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kimi_state.json')
SCENARIOS = {'k2d5': 'SCENARIO_K2D5', 'computer': 'SCENARIO_OK_COMPUTER'}
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
SANDBOX_WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox_workspace')

# Создаем директорию для логов и песочницы если не существуют
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(SANDBOX_WORKDIR, exist_ok=True)


def get_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'chat_id': '', 'parent_id': ''}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def make_connect_frame(obj):
    data = json.dumps(obj, separators=(',', ':')).encode('utf-8')
    return b'\x00' + struct.pack('>I', len(data)) + data


def generate_unique_id():
    """Генерирует уникальный ID для сессии."""
    return hashlib.md5(f"{time.time()}{os.getpid()}".encode()).hexdigest()[:16]


def log_session(message, response, scenario, duration):
    """Сохраняет лог сессии в файл."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f'session_{timestamp}.json')
    log_data = {
        'timestamp': timestamp,
        'scenario': scenario,
        'duration_seconds': duration,
        'user_message': message,
        'ai_response': response
    }
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    return log_file


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
        '-H', 'x-language: en-US', '-H', 'x-msh-device-id: {:id}',
        '-H', 'x-msh-platform: web', '-H', 'x-msh-session-id: {:id}',
        '-H', 'x-msh-shield-data: sg:{:id}',
        '-H', 'x-msh-version: 2.0.0', '-H', 'x-traffic-id: {:id}',
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


# ─── COLORS ──────────────────────────────────────────────────────────
class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BG_CYAN = '\033[46m'
    BG_BLUE = '\033[44m'
    BG_GREEN = '\033[42m'
    BG_RED = '\033[41m'

    @staticmethod
    def color(text, code):
        return f'{code}{text}{C.RESET}'

    @staticmethod
    def success(text):
        return C.color(text, C.GREEN)

    @staticmethod
    def error(text):
        return C.color(text, C.RED)

    @staticmethod
    def warning(text):
        return C.color(text, C.YELLOW)

    @staticmethod
    def info(text):
        return C.color(text, C.CYAN)

    @staticmethod
    def dim(text):
        return C.color(text, C.DIM)

    @staticmethod
    def glow(text):
        return f'{C.BOLD}{C.CYAN}{text}{C.RESET}'


# ─── TERMINAL EFFECTS ────────────────────────────────────────────────
def print_banner():
    """Показывает красивый баннер при запуске."""
    banner = f"""
{C.glow('╔═══════════════════════════════════════════════════════════╗')}
{C.glow('║')}     {C.BOLD}KIMI AI SANDBOX TERMINAL{C.RESET} {C.DIM}v2.0{C.RESET}                     {C.glow('║')}
{C.glow('║')}  {C.DIM}Kimi = мозг и размышление | Terminal = её руки{C.RESET}       {C.glow('║')}
{C.glow('╚═══════════════════════════════════════════════════════════╝')}
"""
    print(banner)


def print_section(title, icon='◆'):
    print(f'\n{C.glow(f"{icon} {title}")}')
    print(f'{C.DIM}{"─" * 60}{C.RESET}')


def print_command_block(cmd, idx, total):
    print(f'\n{C.glow(f"  [{idx}/{total}] {C.BOLD}COMMAND{C.RESET}")}')
    print(f'  {C.WHITE}{C.BOLD}{cmd}{C.RESET}')
    print()


def print_result(result):
    if result['success']:
        print(f'  {C.success("✓ Executed")}')
    else:
        rc = result['returncode']
        print(f'  {C.error(f"✗ Failed (code: {rc})")}')

    if result['stdout']:
        stdout = result['stdout'][:2000]
        total_chars = len(result['stdout'])
        if total_chars > 2000:
            stdout += f'\n{C.dim(f"... ({total_chars} chars total)")}'
        print(f'  {C.DIM}--- STDOUT ---{C.RESET}')
        for line in stdout.split('\n')[:50]:
            print(f'  {line}')
        total_lines = len(result['stdout'].split('\n'))
        if total_lines > 50:
            print(f'  {C.dim(f"... ({total_lines} lines total)")}')

    if result['stderr'] and result['returncode'] != 0:
        stderr = result['stderr'][:1000]
        total_stderr = len(result['stderr'])
        if total_stderr > 1000:
            stderr += f'\n{C.dim("... (truncated)")}'
        print(f'\n  {C.error("--- STDERR ---")}')
        for line in stderr.split('\n')[:30]:
            print(f'  {C.error(line)}')


def print_summary(command_history):
    print(f'\n{C.glow("▸ SANDBOX SESSION COMPLETE")}')
    print(f'  {C.DIM}Commands executed: {len(command_history)}{C.RESET}')

    if command_history:
        print(f'\n  {C.BOLD}Command History:{C.RESET}')
        for i, entry in enumerate(command_history, 1):
            status = C.success('✓') if entry['result']['success'] else C.error('✗')
            cmd_display = entry['command'][:80]
            if len(entry['command']) > 80:
                cmd_display += '...'
            print(f'    {status} {i}. {C.DIM}{cmd_display}{C.RESET}')


def print_thinking(text):
    """Show Kimi's thinking process."""
    print(f'\n{C.glow("◈ THINKING")}')
    print(f'{C.CYAN}{text[:500]}{C.RESET}')
    print()


def print_analysis(text):
    """Show Kimi's final analysis."""
    print()
    print(f'{C.glow("◈ FINAL ANALYSIS")}')
    print(f'{C.CYAN}{text[:3000]}{C.RESET}')
    print()


# ─── EXTRACT COMMANDS FROM RESPONSE ──────────────────────────────────
def extract_commands(text):
    """Extract all JSON commands from Kimi response text."""
    commands = []
    done_flag = False
    thinking_text = ""
    final_answer = ""

    # 1. Try ```json ... ``` or ``` ... ``` blocks ONLY
    json_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    for block in json_blocks:
        block = block.strip()
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                if data.get('done') is True:
                    done_flag = True
                    analysis = data.get('analysis', '')
                    if analysis:
                        final_answer = analysis
                if 'command' in data and isinstance(data['command'], str):
                    commands.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if item.get('done') is True:
                            done_flag = True
                            analysis = item.get('analysis', '')
                            if analysis:
                                final_answer = analysis
                        if 'command' in item and isinstance(item['command'], str):
                            commands.append(item)
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. If no JSON blocks found, try to find standalone JSON objects
    if not commands and not done_flag:
        for obj in re.finditer(r'(?:^|\n)\s*(\{[^{}]+\})', text, re.DOTALL):
            candidate = obj.group(1).strip()
            try:
                data = json.loads(candidate)
                if not isinstance(data, dict):
                    continue
                if 'command' in data and isinstance(data['command'], str):
                    commands.append(data)
                elif data.get('done') is True:
                    done_flag = True
                    analysis = data.get('analysis', '')
                    if analysis:
                        final_answer = analysis
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. If still no commands and no done, check if entire response is a JSON array
    if not commands and not done_flag:
        stripped = text.strip()
        if stripped.startswith('['):
            try:
                data = json.loads(stripped)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            if item.get('done') is True:
                                done_flag = True
                                analysis = item.get('analysis', '')
                                if analysis:
                                    final_answer = analysis
                            if 'command' in item and isinstance(item['command'], str):
                                commands.append(item)
            except (json.JSONDecodeError, TypeError):
                pass

    # 4. Extract thinking text (everything before the first JSON block)
    first_json = re.search(r'```(?:json)?\s*\n', text)
    if not first_json:
        first_json = re.search(r'(?:^|\n)\s*\{[^{}]*"command"', text)
    if first_json:
        thinking_text = text[:first_json.start()].strip()
        if thinking_text and not thinking_text.startswith('{'):
            thinking_text = thinking_text[:1000]

    # 5. If no commands found and no done flag, treat entire response as final answer
    if not commands and not done_flag:
        done_flag = True
        final_answer = text.strip()

    return commands, done_flag, final_answer


# ─── EXECUTE COMMAND IN SANDBOX ──────────────────────────────────────
def execute_command(cmd_str, cwd=None):
    """Execute a command in sandbox directory and return result."""
    # Безопасность: выполняем команды только в sandbox_workspace
    safe_cwd = cwd if cwd and cwd.startswith(SANDBOX_WORKDIR) else SANDBOX_WORKDIR
    
    # Блокируем опасные команды
    dangerous_patterns = ['rm -rf /', 'sudo', 'mkfs', 'dd if=', ':(){:|:&};:', '> /dev/']
    for pattern in dangerous_patterns:
        if pattern in cmd_str:
            return {'stdout': '', 'stderr': f'Command blocked for security: {pattern}', 'returncode': -1, 'success': False}
    
    try:
        result = subprocess.run(
            cmd_str, shell=True, capture_output=True, text=True,
            timeout=120, cwd=safe_cwd
        )
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'success': result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'Command timed out (120s)', 'returncode': -1, 'success': False}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'returncode': -1, 'success': False}


# ─── SANDBOX MODE ────────────────────────────────────────────────────
def run_sandbox_mode(initial_message, auto=False, log_file=None):
    """Sandbox mode: Kimi thinks → we execute → send results back → Kimi analyzes."""
    command_history = []
    total_commands = 0
    round_num = 0
    has_executed_any = False
    start_time = time.time()

    def animate_dots():
        """Show animated dots while waiting for Kimi."""
        for i in range(3):
            sys.stdout.write('.')
            sys.stdout.flush()
            time.sleep(0.5)
        sys.stdout.write('\n')
        sys.stdout.flush()

    try:
        # 1. Send initial message to Kimi
        print_section('INITIALIZING KIMI BRAIN', '⚡')
        print(f'  {C.DIM}Kimi is thinking...{C.RESET}', end=' ')
        animate_dots()
        response = send_message(initial_message, thinking=True, enable_plugin=True, quiet=True)
        print(f'  {C.success("✓")} Ready\n')

        # 2. Loop: Kimi thinks → we execute → send results → repeat
        while True:
            round_num += 1
            print_section(f'ROUND {round_num}', '◈')

            # Extract commands and thinking
            cmd_list, done_flag, thinking_text = extract_commands(response)

            # Show Kimi's thinking
            if thinking_text:
                print_thinking(thinking_text)

            # Check if Kimi signaled completion
            if done_flag:
                # If no commands were ever executed, force Kimi to run commands
                if not has_executed_any:
                    print(f'\n  {C.warning("⚠")} You must execute commands before giving an answer.\n')
                    response = send_message(
                        "You have NOT executed any commands yet. This is FORBIDDEN.\n"
                        "You MUST execute commands to get real data before giving any answer.\n"
                        "Send JSON commands now. Do NOT generate a report.\n",
                        thinking=True, enable_plugin=True, quiet=True
                    )
                    continue
                
                duration = time.time() - start_time
                print_analysis(thinking_text)
                print_summary(command_history)
                
                # Log session
                if log_file:
                    log_session(initial_message, thinking_text, 'sandbox', duration)
                    print(f'\n  {C.info("ℹ")} Session logged to: {log_file}')
                return

            # Extract commands
            if not cmd_list:
                if not has_executed_any:
                    print(f'\n  {C.warning("⚠")} No commands found. Kimi must execute commands first.\n')
                    response = send_message(
                        "You have NOT executed any commands yet. This is FORBIDDEN.\n"
                        "You MUST execute commands to get real data before giving any answer.\n"
                        "Send JSON commands NOW with a \"command\" key containing a real shell command.\n"
                        "Example: {\"command\": \"curl -s https://example.com\"}\n"
                        "Do NOT generate a report. Do NOT send JSON without a \"command\" key.\n",
                        thinking=True, enable_plugin=True, quiet=True
                    )
                    continue
                else:
                    print(f'\n  {C.warning("⚠")} No new commands found. Kimi, please continue analysis.\n')
                    response = send_message(
                        f"You have executed {total_commands} commands so far but have not given a final answer yet.\n"
                        "Analyze the results you have and either:\n"
                        "1. Send more JSON commands if you need additional data\n"
                        "2. Send your FINAL ANSWER as plain text if you have enough info\n"
                        "Do NOT send JSON without a \"command\" key. That is not a valid response.\n",
                        thinking=True, enable_plugin=True, quiet=True
                    )
                    continue

            # Execute commands
            has_executed_any = True
            print_section(f'EXECUTING {len(cmd_list)} COMMANDS', '▸')

            for cmd_idx, cmd_data in enumerate(cmd_list):
                cmd_str = cmd_data['command']
                description = cmd_data.get('description', '')
                total_commands += 1

                print_command_block(cmd_str, cmd_idx + 1, len(cmd_list))
                if description:
                    print(f'  {C.DIM}Description: {description}{C.RESET}')

                print(f'  {C.glow("EXECUTING...")}')
                result = execute_command(cmd_str)
                command_history.append({
                    'command': cmd_str,
                    'result': result
                })
                print_result(result)

            # Build results summary to send back to Kimi
            round_results = f'\n--- Results from Round {round_num} ---\n'
            for i, entry in enumerate(command_history, 1):
                cmd = entry['command']
                res = entry['result']
                round_results += f'\nCommand {i}: {cmd}\n'
                if res['stdout']:
                    round_results += f'STDOUT: {res["stdout"][:500]}\n'
                if res['stderr'] and res['returncode'] != 0:
                    round_results += f'STDERR: {res["stderr"][:500]}\n'
                round_results += f'Success: {res["success"]}\n'
            round_results += f'\nTotal commands executed so far: {total_commands}\n'
            round_results += f'\nPlease analyze these results and either:\n'
            round_results += f'1. Send more commands if you need more information\n'
            round_results += f'2. Send your final answer as plain text if you have enough info\n'

            print(f'\n  {C.info("→")} Sending results back to Kimi...')
            print(f'  {C.DIM}Kimi is analyzing...{C.RESET}', end=' ')
            animate_dots()

            response = send_message(round_results, thinking=True, enable_plugin=True, quiet=True)

    except KeyboardInterrupt:
        print(f'\n\n  {C.warning("⛔")} INTERRUPTED by user')
        print(f'  {C.DIM}Commands executed: {total_commands} | Rounds: {round_num}{C.RESET}\n')
    except Exception as e:
        print(f'\n\n  {C.error("✗")} [SANDBOX] Error: {e}\n')


# ─── ARG PARSING ─────────────────────────────────────────────────────
scenario, thinking, enable_plugin, effort = 'k2d5', True, True, 'LOW'
file_path = None
commands_mode = False
auto_mode = False
enable_logging = False

if '--commands' in sys.argv[1:]:
    commands_mode = True
    sys.argv.remove('--commands')

if '-y' in sys.argv[1:] or '--yes' in sys.argv[1:]:
    auto_mode = True
    sys.argv.remove('-y') if '-y' in sys.argv[1:] else sys.argv.remove('--yes')

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

if '--log' in sys.argv[1:]:
    enable_logging = True
    sys.argv.remove('--log')

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

# ─── MAIN ────────────────────────────────────────────────────────────
if commands_mode:
    print_banner()
    
    if file_path:
        try:
            with open(file_path, 'r') as f:
                user_prompt = f.read()
        except Exception as e:
            print(f'Error reading prompt file: {e}')
            sys.exit(1)
        sandbox_protocol = (
            "\n\n=== SANDBOX PROTOCOL — READ THIS LAST ===\n\n"
            "THIS IS A SANDBOX MODE. You do NOT execute commands yourself.\n"
            "I execute commands for you and return the results.\n\n"
            "YOUR RESPONSE MUST BE EXACTLY ONE OF THESE TWO FORMATS:\n\n"
            "FORMAT A — You need to run commands (JSON in code block ONLY):\n"
            "  ```json\n"
            '  {"command": "curl -s https://example.com"}\n'
            "  ```\n\n"
            "  OR multiple commands:\n"
            "  ```json\n"
            '  [{"command": "curl -s https://a.com"}, {"command": "curl -s https://b.com"}]\n'
            "  ```\n\n"
            "FORMAT B — You have enough data, give final answer (PLAIN TEXT ONLY):\n"
            "  Your analysis here in markdown.\n\n"
            "STRICT RULES:\n"
            "1. FIRST ROUND: You MUST use FORMAT A (JSON in ```json block). No exceptions.\n"
            "2. Do NOT write reports without running commands first.\n"
            "3. Do NOT mix JSON and text in one response.\n"
            "4. The \"command\" value MUST be a real shell command.\n"
            "5. After each round, I send you command results. Then you decide: more commands (FORMAT A) or final answer (FORMAT B).\n"
            "6. If you send FORMAT B without running any commands, you will be rejected.\n"
            "7. ONLY JSON inside ```json blocks will be recognized as commands.\n\n"
            "EXAMPLE FIRST RESPONSE:\n"
            "  ```json\n"
            '  {"command": "curl -s https://target.com"}\n'
            "  ```\n\n"
            "=== END SANDBOX PROTOCOL ===\n"
        )
        sandbox_prompt = user_prompt + sandbox_protocol
    else:
        sandbox_prompt = (
            "Task: " + message + "\n\n"
            "=== SANDBOX PROTOCOL ===\n"
            "You do NOT execute commands. I do.\n"
            "FIRST response MUST be JSON: {\"command\": \"your shell command\"}\n"
            "FINAL response is plain text.\n"
            "Do NOT write reports without running commands.\n"
            "=== END ===\n"
        )
    
    log_path = os.path.join(LOG_DIR, f'sandbox_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json') if enable_logging else None
    run_sandbox_mode(sandbox_prompt, auto=auto_mode, log_file=log_path)
else:
    print_banner()
    start_time = time.time()
    response = send_message(message, scenario, thinking, enable_plugin, effort)
    duration = time.time() - start_time
    
    if enable_logging:
        log_path = log_session(message, response, scenario, duration)
        print(f'\n{C.info("ℹ")} Session logged to: {log_path}')
