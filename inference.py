import sys,re,tools,json,constants
import torch
from transformers import FineGrainedFP8Config, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import time


cls="<|im_start|>"
sep="<|im_end|>"


model2 = "models--Qwen--Qwen3.6-27B/snapshots/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"

print(f"CUDA available: {torch.cuda.is_available()}")

quantization_config = FineGrainedFP8Config()

tokenizer = AutoTokenizer.from_pretrained(
    constants.TRANSFORMERS_DIR+model2
)

print("special_tokens",tokenizer.special_tokens_map)


"""
{'eos_token': '<|im_end|>', 
'pad_token': '<|endoftext|>', 
'audio_bos_token': '<|audio_start|>',
'audio_eos_token': '<|audio_end|>', 
'audio_token': '<|audio_pad|>', 
'image_token': '<|image_pad|>', 
'video_token': '<|video_pad|>', 
'vision_bos_token': '<|vision_start|>', 
'vision_eos_token': '<|vision_end|>'}
"""


model = AutoModelForCausalLM.from_pretrained(
    constants.TRANSFORMERS_DIR+model2,
    device_map="cuda",
    dtype=torch.bfloat16,
    quantization_config=quantization_config,

)
model=torch.compile(model)

def useTool(callStr):
    # print("\n------DETECTED TOOL CALL------\n"+callStr+"\n------------------------------")
    pattern=r"(\w+)\((.*)\)"
    result=re.search(pattern,callStr)
    if not result:
        return "FAILED TO IDENTIFY TOOL CALL"
    tool=result.group(1)
    args=result.group(2)
    # print("------PARSED TOOL CALL------\nTool: "+tool+"\nArgs: "+args+"\n------------------------------")
    for t in tools.TOOLLIST:
        if t.__name__==tool:
            if args=="":
                return t()
            return t(args)

    return "TOOL NOT FOUND"



def generate_response(model, tokenizer, prompt, max_new_tokens:int=100, top_k:int=50, temp:float=0):
    LISTENTOOL = False
    TOOLCALL = ""
    calculated=None

    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)

    for _ in range(max_new_tokens):
        with torch.no_grad():
            outputs = model(input_ids,use_ache=True, past_key_values=calculated)

            calculated=outputs.past_key_values

            outputs=outputs.logits
            next_token_logits = outputs[:, -1, :]


            if temp > 0:
                values, indices = torch.topk(next_token_logits, k=top_k, dim=-1)
                probs = torch.softmax(values / temp, dim=-1)
                sampled_idx = torch.multinomial(probs, num_samples=1)
                next_token_id = indices.gather(-1, sampled_idx)
            else:
                next_token_id = torch.argmax(next_token_logits, dim=-1, keepdim=True)


        #input_ids = torch.cat([input_ids, next_token_id], dim=-1)
        input_ids = next_token_id



        # 只解码新生成的 token 并 yield
        token_str = tokenizer.decode(next_token_id[0], skip_special_tokens=True)
        if token_str=="<tool_call>":
            LISTENTOOL=True
        elif token_str=="</tool_call>":
            LISTENTOOL=False
            result=useTool(TOOLCALL)
            TOOLCALL=""
            # print(result)
            addTokens=tokenizer("\nsystem: "+str(result)+"\nassistant\n<think>\n\n</think>\n\n", return_tensors="pt").input_ids.to(device)
            input_ids = torch.cat([input_ids, addTokens], dim=-1)
        elif LISTENTOOL:
            TOOLCALL+=token_str
        else:
            yield token_str

        if next_token_id.item() == tokenizer.eos_token_id:
           # print("\nEND OF RESPONSE")
            # print(tokenizer.decode(input_ids, skip_special_tokens=False))
            break



"""  Chat Template Jinja

{%- set image_count = namespace(value=0) %}
{%- set video_count = namespace(value=0) %}
{%- macro render_content(content, do_vision_count, is_system_content=false) %}
    {%- if content is string %}
        {{- content }}
    {%- elif content is iterable and content is not mapping %}
        {%- for item in content %}
            {%- if 'image' in item or 'image_url' in item or item.type == 'image' %}
                {%- if is_system_content %}
                    {{- raise_exception('System message cannot contain images.') }}
                {%- endif %}
                {%- if do_vision_count %}
                    {%- set image_count.value = image_count.value + 1 %}
                {%- endif %}
                {%- if add_vision_id %}
                    {{- 'Picture ' ~ image_count.value ~ ': ' }}
                {%- endif %}
                {{- '<|vision_start|><|image_pad|><|vision_end|>' }}
            {%- elif 'video' in item or item.type == 'video' %}
                {%- if is_system_content %}
                    {{- raise_exception('System message cannot contain videos.') }}
                {%- endif %}
                {%- if do_vision_count %}
                    {%- set video_count.value = video_count.value + 1 %}
                {%- endif %}
                {%- if add_vision_id %}
                    {{- 'Video ' ~ video_count.value ~ ': ' }}
                {%- endif %}
                {{- '<|vision_start|><|video_pad|><|vision_end|>' }}
            {%- elif 'text' in item %}
                {{- item.text }}
            {%- else %}
                {{- raise_exception('Unexpected item type in content.') }}
            {%- endif %}
        {%- endfor %}
    {%- elif content is none or content is undefined %}
        {{- '' }}
    {%- else %}
        {{- raise_exception('Unexpected content type.') }}
    {%- endif %}
{%- endmacro %}
{%- if not messages %}
    {{- raise_exception('No messages provided.') }}
{%- endif %}
{%- if tools and tools is iterable and tools is not mapping %}
    {{- '<|im_start|>system\n' }}
    {{- "# Tools\n\nYou have access to the following functions:\n\n<tools>" }}
    {%- for tool in tools %}
        {{- "\n" }}
        {{- tool | tojson }}
    {%- endfor %}
    {{- "\n</tools>" }}
    {{- '\n\nIf you choose to call a function ONLY reply in the following format with NO suffix:\n\n<tool_call>\n<function=example_function_name>\n<parameter=example_parameter_1>\nvalue_1\n</parameter>\n<parameter=example_parameter_2>\nThis is the value for the second parameter\nthat can span\nmultiple lines\n</parameter>\n</function>\n</tool_call>\n\n<IMPORTANT>\nReminder:\n- Function calls MUST follow the specified format: an inner <function=...></function> block must be nested within <tool_call></tool_call> XML tags\n- Required parameters MUST be specified\n- You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after\n- If there is no function call available, answer the question like normal with your current knowledge and do not tell the user about function calls\n</IMPORTANT>' }}
    {%- if messages[0].role == 'system' %}
        {%- set content = render_content(messages[0].content, false, true)|trim %}
        {%- if content %}
            {{- '\n\n' + content }}
        {%- endif %}
    {%- endif %}
    {{- '<|im_end|>\n' }}
{%- else %}
    {%- if messages[0].role == 'system' %}
        {%- set content = render_content(messages[0].content, false, true)|trim %}
        {{- '<|im_start|>system\n' + content + '<|im_end|>\n' }}
    {%- endif %}
{%- endif %}
{%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
{%- for message in messages[::-1] %}
    {%- set index = (messages|length - 1) - loop.index0 %}
    {%- if ns.multi_step_tool and message.role == "user" %}
        {%- set content = render_content(message.content, false)|trim %}
        {%- if not(content.startswith('<tool_response>') and content.endswith('</tool_response>')) %}
            {%- set ns.multi_step_tool = false %}
            {%- set ns.last_query_index = index %}
        {%- endif %}
    {%- endif %}
{%- endfor %}
{%- if ns.multi_step_tool %}
    {{- raise_exception('No user query found in messages.') }}
{%- endif %}
{%- for message in messages %}
    {%- set content = render_content(message.content, true)|trim %}
    {%- if message.role == "system" %}
        {%- if not loop.first %}
            {{- raise_exception('System message must be at the beginning.') }}
        {%- endif %}
    {%- elif message.role == "user" %}
        {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>' + '\n' }}
    {%- elif message.role == "assistant" %}
        {%- set reasoning_content = '' %}
        {%- if message.reasoning_content is string %}
            {%- set reasoning_content = message.reasoning_content %}
        {%- else %}
            {%- if '</think>' in content %}
                {%- set reasoning_content = content.split('</think>')[0].rstrip('\n').split('<think>')[-1].lstrip('\n') %}
                {%- set content = content.split('</think>')[-1].lstrip('\n') %}
            {%- endif %}
        {%- endif %}
        {%- set reasoning_content = reasoning_content|trim %}
        {%- if (preserve_thinking is defined and preserve_thinking is true) or (loop.index0 > ns.last_query_index) %}
            {{- '<|im_start|>' + message.role + '\n<think>\n' + reasoning_content + '\n</think>\n\n' + content }}
        {%- else %}
            {{- '<|im_start|>' + message.role + '\n' + content }}
        {%- endif %}
        {%- if message.tool_calls and message.tool_calls is iterable and message.tool_calls is not mapping %}
            {%- for tool_call in message.tool_calls %}
                {%- if tool_call.function is defined %}
                    {%- set tool_call = tool_call.function %}
                {%- endif %}
                {%- if loop.first %}
                    {%- if content|trim %}
                        {{- '\n\n<tool_call>\n<function=' + tool_call.name + '>\n' }}
                    {%- else %}
                        {{- '<tool_call>\n<function=' + tool_call.name + '>\n' }}
                    {%- endif %}
                {%- else %}
                    {{- '\n<tool_call>\n<function=' + tool_call.name + '>\n' }}
                {%- endif %}
                {%- if tool_call.arguments is defined %}
                    {%- for args_name, args_value in tool_call.arguments|items %}
                        {{- '<parameter=' + args_name + '>\n' }}
                        {%- set args_value = args_value | string if args_value is string else args_value | tojson | safe %}
                        {{- args_value }}
                        {{- '\n</parameter>\n' }}
                    {%- endfor %}
                {%- endif %}
                {{- '</function>\n</tool_call>' }}
            {%- endfor %}
        {%- endif %}
        {{- '<|im_end|>\n' }}
    {%- elif message.role == "tool" %}
        {%- if loop.previtem and loop.previtem.role != "tool" %}
            {{- '<|im_start|>user' }}
        {%- endif %}
        {{- '\n<tool_response>\n' }}
        {{- content }}
        {{- '\n</tool_response>' }}
        {%- if not loop.last and loop.nextitem.role != "tool" %}
            {{- '<|im_end|>\n' }}
        {%- elif loop.last %}
            {{- '<|im_end|>\n' }}
        {%- endif %}
    {%- else %}
        {{- raise_exception('Unexpected message role.') }}
    {%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}

"""

def readManual():
    with open("Manual.md","r",encoding="utf-8") as f:
        return f.read()
text=cls+f"system\n{readManual()}\nUse any tools as needed.\nuser: Post an article that suits the theme of the website. Read existing articles to guide you on the theme. Write a length similar to existing articles but no more than 2000 words.废话少说！建议非理性过度解读！\nassistant\n<think>\n\n</think>\n\n"
# print(text)

# 逐token打印
for token in generate_response(model, tokenizer, text, 50000000, temp=0.7):
    print(token, end="", flush=True)
print()  # 换行