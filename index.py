import streamlit as st
from docx import Document
import google.generativeai as genai
import os
import asyncio
import io
import json

# --- 全局变量 ---
# 从 Vercel 环境变量中获取 API 密钥
api_key = os.environ.get("GOOGLE_API_KEY")

# 检查是否成功获取 API 密钥
if not api_key:
    st.error("未设置 GOOGLE_API_KEY 环境变量！")
    st.stop()  # 停止应用加载

# 设置 API 密钥
genai.configure(api_key=api_key)

# 选择 Gemini Pro 模型
model = genai.GenerativeModel('gemini-1.5-flash')

# Streamlit 应用标题
st.title("Word 文档翻译")

# 文件上传
uploaded_file = st.file_uploader("上传 Word 文档 (.docx)", type=["docx"])

# 目标语言选择
target_language = st.selectbox("选择目标语言", ["zh-CN", "en", "ja", "ko", "fr", "de", "es"])

# 双语模式选择
bilingual = st.checkbox("双语对照模式", False)

# --- 翻译进度条 ---
progress_bar = st.progress(0, text="准备翻译...")
progress_lock = asyncio.Lock() 
total_elements = 0
completed_elements = 0


async def update_progress(completed):
    """更新进度条"""
    async with progress_lock:
        progress = int(completed)
        progress_bar.progress(progress, text=f"正在翻译... ({progress}%)")


async def translate_text(texts):
    """使用 Google Gemini API 批量翻译文本"""
    # 设置最大 token 限制
    max_tokens = 8000

    # 构建通用的 prompt
    prompt = f"""
                Translate the following texts to {target_language}, paying close attention to the context and ensuring accuracy. Double-check for any potentially ambiguous words or phrases and choose the most appropriate translation. 


                **Examples of potential ambiguities:**
                - If the word "charge" refers to billing, ensure it is not translated as "charging" (as in electricity).

                **Formatting instructions:**
                - Do not add any extra line breaks, markdown formatting, numbering, or any other special formatting. 
                - Please preserving all original formatting, including spaces, line breaks, and special characters such as tabs.
                - Directly return a JSON array without any additional formatting. 
                - Only return the translated texts in the following JSON format:
                A JSON array where each element contains an "index" field and a "translation" field.

                Please translate the following texts:
                """
    # 将文本列表分割成多个批次，每个批次的 token 数量不超过最大限制
    batches = []
    current_batch = []
    current_tokens = 0
    for i, text in enumerate(texts):
        text_tokens = len(text)
        if current_tokens + text_tokens > max_tokens:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append((i, text))
        current_tokens += text_tokens
    if current_batch:
        batches.append(current_batch)

    # 依次翻译每个批次
    translations = []
    total_batches = len(batches)
    for batch_index, batch in enumerate(batches):
        # 计算当前批次的进度范围
        batch_start = int(batch_index / total_batches * 100 + 1)
        batch_end = int((batch_index + 1) / total_batches * 100)
        await update_progress(batch_start + 20)  # 开始调用 Gemini API 前，设为起始值 + 20%

        batch_prompt = prompt  # 使用通用的 prompt
        for i, text in batch:
            batch_prompt += f"{i}. {text}\n"  # 添加文本内容

        response = model.generate_content(batch_prompt)
        batch_translations = response.text
        await update_progress(batch_end - 10)  # 调用 Gemini API 后，设为结束值 - 10%

        # 移除 ```json ``` 包装
        if batch_translations.startswith("```json\n") and batch_translations.endswith("\n```"):
            batch_translations = batch_translations[8:-4].strip()

        # 使用 replace() 方法替换无效字符
        batch_translations = ''.join(c for c in batch_translations if c.isprintable())

        try:
            batch_translations = json.loads(batch_translations)
            translations.extend(batch_translations)
            await update_progress(batch_end)  # 处理完批次后，设为结束值
        except Exception as e:
            st.exception(e)  # 显示完整的错误堆栈

    translations.sort(key=lambda x: int(x['index']))  # 将 index 转换为整数
    return [t['translation'].rstrip() for t in translations]


async def process_paragraph(paragraph, translations, paragraph_index):
    """处理单个段落，包含翻译和进度更新"""
    run = paragraph.runs[0]
    for aRun in paragraph.runs:
        original_text = aRun.text.strip()
        if original_text:
            run = aRun
            break

    if bilingual:
        new_run = paragraph.add_run("\n"+translations[paragraph_index])
        if run:
            # 在 translations 中查找对应的翻译结果
            new_run.font.bold = run.font.bold
            new_run.font.italic = run.font.italic
            new_run.font.underline = run.font.underline
            new_run.font.color.rgb = run.font.color.rgb
    else:
        paragraph.text = translations[paragraph_index]
        if run:
           for new_run in paragraph.runs:
               new_run.font.bold = run.font.bold
               new_run.font.italic = run.font.italic
               new_run.font.underline = run.font.underline
               new_run.font.color.rgb = run.font.color.rgb

async def translate_document(document):
    """使用 asyncio 异步翻译文档"""
    global total_elements, completed_elements
    total_elements = 0
    texts_to_translate = []

    for paragraph in document.paragraphs:
        original_text = paragraph.text.strip()
        if original_text:
            texts_to_translate.append(paragraph.text)
            total_elements += 1

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original_text = paragraph.text.strip()
                    if original_text:
                        texts_to_translate.append(paragraph.text)
                        total_elements += 1

    completed_elements = 0

    translations = await translate_text(texts_to_translate)

    tasks = []
    current_paragraph_index = 0
    for paragraph in document.paragraphs:
        original_text = paragraph.text.strip()
        if original_text:
            tasks.append(
                asyncio.create_task(
                    process_paragraph(paragraph, translations, current_paragraph_index)
                )
            )
            current_paragraph_index += 1

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original_text = paragraph.text.strip()
                    if original_text:
                        tasks.append(
                            asyncio.create_task(
                                process_paragraph(paragraph, translations, current_paragraph_index)
                            )
                        )
                        current_paragraph_index += 1

    await asyncio.gather(*tasks)
    return document


# 翻译按钮
if st.button("开始翻译") and uploaded_file is not None:
    try:
        # 读取 Word 文档
        doc = Document(uploaded_file)

        # 使用 asyncio 运行异步函数
        translated_doc = asyncio.run(translate_document(doc))

        # 将翻译后的文档保存到内存中
        output = io.BytesIO()
        translated_doc.save(output)
        output.seek(0)

        # 提供下载链接
        st.download_button(
            label="下载翻译后的文档",
            data=output.getvalue(),
            file_name=f"translated_{uploaded_file.name}",
        )

    except Exception as e:
        st.error(f"翻译过程中出现错误：{e}")
        st.exception(e)  # 显示完整的错误堆栈