import subprocess
import sys

def run_python_code(code, input_data="", inject_var=None, function_name=None):
    python_cmd = 'python' if sys.platform == 'win32' else 'python3'

    # Build the code to run
    user_code = code  # default — no injection

    if inject_var:
        prefix = ""
        try:
            val = eval(input_data) if isinstance(input_data, str) else input_data
            if isinstance(val, dict):
                for k, v in val.items():
                    prefix += f"{k} = {repr(v)}\n"
            else:
                var_names = [v.strip() for v in inject_var.replace(',', '\n').split('\n') if v.strip()]
                if isinstance(val, (list, tuple)) and len(var_names) > 1:
                    for i, name in enumerate(var_names):
                        prefix += f"{name} = {repr(val[i])}\n"
                else:
                    prefix = f"{var_names[0]} = {repr(val)}\n"
        except:
            var_names = [v.strip() for v in inject_var.replace(',', '\n').split('\n') if v.strip()]
            prefix = f"{var_names[0]} = {repr(input_data)}\n"
        user_code = prefix + code

    # If a function_name is given and student didn't print anything themselves,
    # auto-call the function and print its return value (LeetCode style)
    if function_name:
        var_names = [v.strip() for v in inject_var.replace(',', '\n').split('\n') if v.strip()] if inject_var else []
        call_args = ', '.join(var_names)
        auto_call = f"\n_result = {function_name}({call_args})\nif _result is not None: print(_result)\n"
        # Only auto-call if there's no explicit print in user code
        if 'print(' not in user_code:
            user_code = user_code + auto_call

    # Wrap in sandbox
    sandbox = """
import sys

BLOCKED = {
    'os', 'sys', 'subprocess', 'shutil', 'pathlib', 'socket',
    'requests', 'urllib', 'http', 'ftplib', 'smtplib',
    'importlib', 'builtins', 'ctypes', 'multiprocessing',
    'threading', 'signal', 'pty', 'tty', 'termios',
    'pwd', 'grp', 'resource', 'syslog', 'platform',
    'winreg', 'winsound', 'msvcrt',
}

original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

def blocked_import(name, *args, **kwargs):
    base = name.split('.')[0]
    if base in BLOCKED:
        raise ImportError(f"Module '{name}' is not allowed.")
    return original_import(name, *args, **kwargs)

__builtins__.__import__ = blocked_import

def blocked_open(*args, **kwargs):
    raise PermissionError("File access is not allowed.")

__builtins__.open = blocked_open
__builtins__.exec = lambda *a, **k: (_ for _ in ()).throw(PermissionError("exec() is not allowed."))

# ── USER CODE BELOW ──
""" + user_code

    try:
        process = subprocess.run(
            [python_cmd, '-c', sandbox],
            input=input_data if not inject_var else "",
            capture_output=True,
            text=True,
            timeout=2.0
        )
        return process.stdout.strip(), process.stderr

    except subprocess.TimeoutExpired:
        return None, "TIMEOUT: Infinite loop detected"
    except Exception as e:
        return None, str(e)