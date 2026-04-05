import openai
import time
import random
import os
import base64
from openai import OpenAI
import time
import json
import pathlib
from types import SimpleNamespace


# Read and cache once
_CFG_PATH = pathlib.Path(__file__).with_name("api_config.json")
with _CFG_PATH.open("r", encoding="utf-8") as _f:
    _CFG = json.load(_f)


def cfg(svc: str, key: str, default=None):
    env_value = os.getenv(f"{svc}_{key}".upper())
    if env_value is not None:
        return env_value

    if key == "api_key" and svc != "iconfinder":
        shared_env_value = os.getenv("OPENAI_API_KEY")
        if shared_env_value is not None:
            return shared_env_value

        shared_cfg_value = _CFG.get("api_key")
        if shared_cfg_value is not None:
            return shared_cfg_value

    return _CFG.get(svc, {}).get(key, default)


def generate_log_id():
    """Generate a log ID with 'tkb' prefix and current timestamp."""
    return f"tkb{int(time.time() * 1000)}"


def request_claude(prompt, log_id=None, max_tokens=16384, max_retries=3):
    base_url = cfg("claude", "base_url")
    api_key = cfg("claude", "api_key")
    model_name = cfg("claude", "model")
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=600.0)

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            response = client.chat.completions.create(
                model = model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_claude_token(prompt, log_id=None, max_tokens=10000, max_retries=3):
    base_url = cfg("claude", "base_url")
    api_key = cfg("claude", "api_key")
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=600.0)
    model_name = cfg("claude", "model")
    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            # Use streaming to prevent timeouts on long generations (Keep-Alive)
            stream = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                stream=True,
                stream_options={"include_usage": True},
            )
            
            collected_content = []
            
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        collected_content.append(delta.content)
                
                # Usage is typically in the last chunk
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info["prompt_tokens"] = chunk.usage.prompt_tokens
                    usage_info["completion_tokens"] = chunk.usage.completion_tokens
                    usage_info["total_tokens"] = chunk.usage.total_tokens

            full_content = "".join(collected_content)

            # Construct a MockResponse object compatible with agent.py expectations
            # agent.py checks:
            # 1. response.candidates[0].content.parts[0].text (Gemini style)
            # 2. response.choices[0].message.content (OpenAI style)
            
            class MockResponse:
                def __init__(self, content, usage):
                    self.content_str = content
                    self.usage = SimpleNamespace(**usage) if usage else None
                    
                    # OpenAI style
                    self.choices = [
                        SimpleNamespace(message=SimpleNamespace(content=content))
                    ]
                    
                    # Gemini style (just in case)
                    self.candidates = [
                        SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=content)]))
                    ]
                
                def __str__(self):
                    return self.content_str

            return MockResponse(full_content, usage_info), usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

    return None, usage_info

def request_gemini_with_video(prompt: str, video_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10):
    """
    Makes a multimodal request to the Gemini model using video + text via OpenAI-compatible proxy.
    """
    base_url = cfg("gemini", "base_url")
    # api_version = cfg("gemini", "api_version") # Standard OpenAI proxy usually doesn't need api_version in init
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # 修改点：使用 base_url 初始化标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    data_url = f"data:video/mp4;base64,{video_base64}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}, "media_type": "video/mp4"},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)


def request_gemini_video_img(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10
):
    """
    Makes a multimodal request to the Gemini model using video & ref img + text via OpenAI-compatible proxy.
    """
    base_url = cfg("gemini", "base_url")
    # api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # 修改点：使用 base_url 初始化标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                                "media_type": "video/mp4",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                                "media_type": "image/png",
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None


def request_gemini_video_img_token(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10
):
    """
    Makes a multimodal request to the Gemini model using video & ref img + text (Returns Token Usage).
    """
    base_url = cfg("gemini", "base_url")
    # api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # 修改点：使用 base_url 初始化标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                                "media_type": "video/mp4",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                                "media_type": "image/png",
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            # return completion

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None, usage_info


def request_gemini(prompt, log_id=None, max_tokens=8000, max_retries=10):
    """
    Makes a request to the Gemini model via OpenAI-compatible proxy.
    """
    base_url = cfg("gemini", "base_url")
    # api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # 修改点：使用 base_url 初始化标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gemini_token(prompt, log_id=None, max_tokens=8000, max_retries=10):
    """
    Makes a request to the Gemini model via OpenAI-compatible proxy (Returns Token Usage).
    """

    base_url = cfg("gemini", "base_url")
    # api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # 修改点：使用 base_url 初始化标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info

def request_gpt4o(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gpt-4o-2024-11-20 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """

    base_url = cfg("gpt4o", "base_url")
    api_version = cfg("gpt4o", "api_version")
    ak = cfg("gpt4o", "api_key")
    model_name = cfg("gpt4o", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion.choices[0].message.content
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt4o_token(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gpt-4o model with retry functionality.
    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4o", "base_url")
    ak = cfg("gpt4o", "api_key")
    model_name = cfg("gpt4o", "model")

    # --- MODIFIED: Use standard OpenAI client & 5 min timeout ---
    client = OpenAI(
        base_url=base_url,
        api_key=ak,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=300.0
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"Failed after {max_retries} attempts. Last error: {str(e)}")
                return None, usage_info

            # Exponential backoff with jitter
            delay = (2**retry_count) * 1.0 + (random.random() * 0.5)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_o4mini(prompt, log_id=None, max_tokens=8000, max_retries=3, thinking=False):
    """
    Makes a request to the o4-mini-2025-04-16 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        thinking (bool, optional): Whether to enable thinking mode, default False

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4omini", "base_url")
    api_version = cfg("gpt4omini", "api_version")
    ak = cfg("gpt4omini", "api_key")
    model_name = cfg("gpt4omini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Configure extra_body for thinking if enabled
    extra_body = None
    if thinking:
        extra_body = {"thinking": {"type": "enabled", "budget_tokens": 2000}}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_o4mini_token(prompt, log_id=None, max_tokens=8000, max_retries=3, thinking=False):
    """
    Makes a request to the o4-mini-2025-04-16 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        thinking (bool, optional): Whether to enable thinking mode, default False

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4omini", "base_url")
    api_version = cfg("gpt4omini", "api_version")
    ak = cfg("gpt4omini", "api_key")
    model_name = cfg("gpt4omini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Configure extra_body for thinking if enabled
    extra_body = None
    if thinking:
        extra_body = {"thinking": {"type": "enabled", "budget_tokens": 2000}}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_gpt5(prompt, log_id=None, max_tokens=1000, max_retries=10):
    """
    Makes a request to the gpt-5 model via standard OpenAI client.
    (No token usage return, just the completion object)
    """
    # 1. 读取配置
    base_url = cfg("gpt5", "base_url")
    ak = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    # 2. ✅ 修正点：改为标准 OpenAI 客户端
    client = OpenAI(
        base_url=base_url,
        api_key=ak,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=300.0
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

def request_gpt5_token(prompt, log_id=None, max_tokens=1000, max_retries=10):
    """
    Makes a request to the gpt-5 model via standard OpenAI client.
    """
    # 1. 读取配置
    base_url = cfg("gpt5", "base_url")
    ak = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    # 2. ✅ 修正点：标准 OpenAI 客户端使用 base_url，而不是 azure_endpoint
    client = OpenAI(
        base_url=base_url,  # 👈 注意这里改成了 base_url
        api_key=ak,
        timeout=600.0,      # 设置 10 分钟超时
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=300.0
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"Failed after {max_retries} attempts. Last error: {str(e)}")
                return None, usage_info

            delay = (2**retry_count) * 1.0 + (random.random() * 0.5)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info

def request_gpt5_img(prompt, image_path=None, log_id=None, max_tokens=1000, max_retries=10):
    """
    Makes a request to the gpt-5 model with optional image input.
    Uses standard OpenAI client.
    """
    # 1. 读取配置
    base_url = cfg("gpt5", "base_url")
    ak = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    # 2. 初始化标准客户端
    client = OpenAI(
        base_url=base_url,
        api_key=ak,
        timeout=600.0,
    )
    
    if log_id is None:
        log_id = generate_log_id()
    
    # 部分中转商可能不支持自定义 header，如果报错可注释掉
    extra_headers = {"X-TT-LOGID": log_id}

    # 3. 构建消息体
    if image_path:
        # 检查图片是否存在
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # 读取并转为 Base64
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}",
                            "detail": "high" # 强制高清模式
                        }
                    },
                ],
            }
        ]
    else:
        # 如果没有图片，就当普通对话处理
        messages = [{"role": "user", "content": prompt}]

    # 4. 发送请求
    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=300.0
            )
            return completion
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            
            delay = (2**retry_count) * 1.0 + (random.random() * 0.5)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

def request_gpt5_with_video(prompt: str, video_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10):
    """
    [GPT-5] Video + Text Request.
    Mimics Gemini's video handling. 
    Note: Standard OpenAI models usually expect frames, but this sends base64 video stream 
    relying on the proxy/model's native multimodal capabilities.
    """
    base_url = cfg("gpt5", "base_url")
    api_key = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0, # 视频处理通常需要更长时间，建议设为 600s
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    data_url = f"data:video/mp4;base64,{video_base64}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            # 仿照 Gemini 的结构发送视频
                            # 注意：如果标准 GPT-4o 报错，这里可能需要改为发送图片帧列表
                            {
                                "type": "image_url", 
                                "image_url": {"url": data_url, "detail": "high"}, 
                                # 这里的 media_type 是为了兼容部分中转站对 Gemini 格式的识别
                                # 标准 OpenAI 库可能会忽略这个额外字段，但在 payload 中会保留
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=600.0
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            
            delay = (2**retry_count) * 0.5 + (random.random() * 0.5)
            print(f"GPT-5 Video Retry {retry_count}/{max_retries}: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)


def request_gpt5_video_img(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10
):
    """
    [GPT-5] Video + Reference Image + Text Request.
    Mimics request_gemini_video_img.
    """
    base_url = cfg("gpt5", "base_url")
    api_key = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # 1. Process Video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    # 2. Process Image
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=600.0
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.5 + (random.random() * 0.5)
            print(f"GPT-5 Video+Img Retry {retry_count}/{max_retries}: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None


def request_gpt5_video_img_token(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 10
):
    """
    [GPT-5] Video + Reference Image + Text Request (Returns Token Usage).
    Mimics request_gemini_video_img_token.
    """
    base_url = cfg("gpt5", "base_url")
    api_key = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # 1. Process Video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    # 2. Process Image
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=600.0
            )
            
            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.5 + (random.random() * 0.5)
            print(f"GPT-5 Video+Img+Token Retry {retry_count}/{max_retries}: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None, usage_info

def request_gpt41(prompt, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-4.1-2025-04-14 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt41", "base_url")
    api_version = cfg("gpt41", "api_version")
    api_key = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
        timeout=600.0,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt41_token(prompt, log_id=None, max_tokens=1000, max_retries=3):
    # 读取配置
    base_url = cfg("gpt41", "base_url")
    ak = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    # --- MODIFIED: Use standard OpenAI client & 5 min timeout ---
    client = OpenAI(
        base_url=base_url,
        api_key=ak,
        timeout=600.0,
    )
    # ------------------------------------

    if log_id is None:
        log_id = generate_log_id()

    # 某些中转站不支持自定义 header，如果报错可以把 extra_headers 删掉
    extra_headers = {"X-TT-LOGID": log_id} 
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                timeout=300.0
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                # 即使失败也返回，以免程序崩溃
                print(f"Failed after {max_retries} attempts. Last error: {str(e)}")
                return None, usage_info
            
            # 增加重试等待时间
            delay = (2**retry_count) * 1.0 + (random.random() * 0.5)
            print(f"Retry {retry_count} error: {str(e)}. Waiting {delay:.2f}s...")
            time.sleep(delay)

    return None, usage_info


def request_gpt41_img(prompt, image_path=None, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-4.1-2025-04-14 model with optional image input and retry functionality.
    Args:
        prompt (str): The text prompt to send to the model
        image_path (str, optional): Absolute path to an image file to include
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3
    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt41", "base_url")
    api_version = cfg("gpt41", "api_version")
    ak = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
        timeout=600.0,
    )
    if log_id is None:
        log_id = generate_log_id()
    extra_headers = {"X-TT-LOGID": log_id}

    if image_path:
        # 检查图片路径是否存在
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ],
            }
        ]

    else:
        messages = [{"role": "user", "content": prompt}]
    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


if __name__ == "__main__":

    # Gemini
    # response_gemini = request_gemini("上海天气怎么样？")
    # print(response_gemini.model_dump_json())

    # # GPT-4o
    # response_gpt4o = request_gpt4o("上海天气怎么样？")
    # print(response_gpt4o)

    # # o4-mini
    # response_o4mini = request_o4mini("上海天气怎么样？")
    # print(response_o4mini.model_dump_json())

    # # GPT-4.1
    #response_gpt41 = request_gpt41("上海天气怎么样？")
    #print(response_gpt41.model_dump_json())

    # GPT-5
    # response_gpt5 = request_gpt5("新加坡天气怎么样？")
    # print(response_gpt5.model_dump_json())

    # Claude
    response_claude = request_claude_token("新加坡天气怎么样？")
    print(response_claude)
    
    # 测试 prompt
    # print("\n🚀 开始【混合架构】全功能测试 (Hybrid Agent Debug)...")
    # print("🎯 目标架构: GPT-5 (大脑/代码) + Gemini (眼睛/视频)")
    # print("=" * 60)

    # # ==========================================
    # # 1. 测试 GPT-5 (大脑/代码生成能力)
    # # ==========================================
    # print("1️⃣ [大脑测试] 正在请求 GPT-5 (request_gpt5_token) ...")
    # prompt_text = "你好，请用中文简短介绍一下你自己，并写一个简单的Python Hello World 函数。"
    
    # try:
    #     start_time = time.time()
    #     # 调用 GPT-5 接口
    #     response, usage = request_gpt5_token(prompt_text)
    #     duration = time.time() - start_time
        
    #     if response:
    #         print(f"✅ GPT-5 请求成功 (耗时 {duration:.2f}s)")
    #         # 解析内容
    #         try:
    #             content = response.choices[0].message.content
    #             # 🔴 修改点：去掉了 [:100]，打印完整内容
    #             print(f"💬 模型回复:\n{content.strip()}") 
    #         except Exception:
    #             print(f"⚠️ 无法解析回复内容，原始对象: {response}")
    #         print(f"📊 Token数据: {usage}")
    #     else:
    #         print("❌ GPT-5 请求失败: 返回为空")
            
    # except Exception as e:
    #     print(f"❌ GPT-5 测试发生异常: {e}")
    
    # print("-" * 60)

    # # ==========================================
    # # 2. 测试 Gemini (眼睛/视频理解能力)
    # # ==========================================
    # print("2️⃣ [眼睛测试] 正在请求 Gemini (request_gemini_video_img_token) ...")
    
    # # 自动定位项目中的测试资源
    # current_dir = pathlib.Path(__file__).parent.resolve()
    
    # # 1. 寻找一张存在的图片
    # image_path = current_dir / "assets" / "reference" / "GRID.png"
    # if not image_path.exists():
    #     image_path = current_dir / "assets" / "icon" / "cat.png"

    # # 2. 设置视频路径 
    # video_path = current_dir / "CASES" / "test_video.mp4" 

    # print(f"📂 图片路径: {image_path}")
    # print(f"📂 视频路径: {video_path}")

    # if image_path.exists() and video_path.exists():
    #     print("▶️ 文件存在，开始发送多模态请求 (Gemini)...")
    #     prompt_mm = "请详细描述这张图片的内容，并分析视频中发生的事情。"
        
    #     try:
    #         start_time = time.time()
    #         # 调用 Gemini 多模态接口
    #         response_mm, usage_mm = request_gemini_video_img_token(prompt_mm, str(video_path), str(image_path))
    #         duration = time.time() - start_time
            
    #         if response_mm:
    #             print(f"✅ Gemini 多模态请求成功 (耗时 {duration:.2f}s)")
    #             try:
    #                 # 兼容不同格式的解析
    #                 if hasattr(response_mm, 'choices'):
    #                     content_mm = response_mm.choices[0].message.content
    #                 elif hasattr(response_mm, 'candidates'):
    #                     content_mm = response_mm.candidates[0].content.parts[0].text
    #                 else:
    #                     content_mm = str(response_mm)
                    
    #                 # 🔴 修改点：去掉了 [:100]，打印完整内容
    #                 print(f"💬 模型回复:\n{content_mm.strip()}") 
    #             except Exception:
    #                 print(f"⚠️ 无法解析回复内容")
    #             print(f"📊 Token数据: {usage_mm}")
    #         else:
    #             print("❌ Gemini 多模态请求失败: 返回为空")
    #     except Exception as e:
    #         print(f"❌ Gemini 多模态测试发生异常: {e}")
    # else:
    #     print("⚠️ 跳过 Gemini 测试: 未找到测试文件 (test_video.mp4 或 图片)。")

    # print("=" * 60)
    # print("🚀 测试结束。如果以上两步都成功，您可以放心运行 agent.py 混合任务了。")
