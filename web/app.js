const state = {
  projectId: null,
  pendingFiles: [],
  selectedTopic: null,
  scriptMarkdown: "",
};

const el = {
  provider: document.querySelector("#provider"),
  thinking: document.querySelector("#thinking"),
  thinkingTitle: document.querySelector("#thinkingTitle"),
  thinkingPercent: document.querySelector("#thinkingPercent"),
  thinkingStep: document.querySelector("#thinkingStep"),
  progressBar: document.querySelector("#progressBar"),
  steps: document.querySelector("#steps"),
  idea: document.querySelector("#idea"),
  asset: document.querySelector("#asset"),
  assetList: document.querySelector("#assetList"),
  startBtn: document.querySelector("#startBtn"),
  analysis: document.querySelector("#analysis"),
  questionBox: document.querySelector("#questionBox"),
  topicBtn: document.querySelector("#topicBtn"),
  topicHint: document.querySelector("#topicHint"),
  topics: document.querySelector("#topics"),
  script: document.querySelector("#script"),
  scriptStatus: document.querySelector("#scriptStatus"),
  copyBtn: document.querySelector("#copyBtn"),
  downloadBtn: document.querySelector("#downloadBtn"),
  toast: document.querySelector("#toast"),
};

function toast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  window.setTimeout(() => el.toast.classList.remove("show"), 2400);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "请求失败";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  return response.json();
}

function setBusy(button, busy, text) {
  if (!button) return;
  button.disabled = busy;
  if (text) {
    button.dataset.idleText = button.dataset.idleText || button.textContent;
    button.textContent = busy ? text : button.dataset.idleText;
  }
}

function updateStep(activeStep) {
  const order = ["input", "analysis", "questions", "topics", "script"];
  const activeIndex = order.indexOf(activeStep);
  el.steps.querySelectorAll("li").forEach((item) => {
    const itemIndex = order.indexOf(item.dataset.step);
    item.classList.toggle("active", item.dataset.step === activeStep);
    item.classList.toggle("done", itemIndex >= 0 && itemIndex < activeIndex);
  });
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function runThinking(title, steps, minimumMs = 1900) {
  el.thinking.classList.remove("hidden");
  el.thinkingTitle.textContent = title;
  el.progressBar.style.width = "0%";
  el.thinkingPercent.textContent = "0%";
  el.thinkingStep.textContent = steps[0] || "正在处理...";

  const stepDelay = Math.max(320, Math.floor(minimumMs / Math.max(steps.length, 1)));
  for (let index = 0; index < steps.length; index += 1) {
    const percent = Math.min(92, Math.round(((index + 1) / steps.length) * 86));
    el.thinkingStep.textContent = steps[index];
    el.progressBar.style.width = `${percent}%`;
    el.thinkingPercent.textContent = `${percent}%`;
    await sleep(stepDelay);
  }
}

async function finishThinking(finalStep = "完成") {
  el.thinkingStep.textContent = finalStep;
  el.progressBar.style.width = "100%";
  el.thinkingPercent.textContent = "100%";
  await sleep(420);
  el.thinking.classList.add("hidden");
}

function renderAssets() {
  el.assetList.innerHTML = "";
  state.pendingFiles.forEach((file) => {
    const item = document.createElement("li");
    const size = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
    item.innerHTML = `<span>${file.name}</span><span>${size}</span>`;
    el.assetList.appendChild(item);
  });
}

async function loadModelStatus() {
  try {
    const status = await api("/api/model-status");
    if (status.provider === "openai") {
      el.provider.textContent = `模型：OpenAI / ${status.openai_model}`;
    } else if (status.provider === "gemini") {
      el.provider.textContent = `模型：Gemini / ${status.gemini_model}`;
    } else {
      el.provider.textContent = "模型：本地规则";
    }
  } catch {
    el.provider.textContent = "模型：状态未知";
  }
}

function renderAnalysis(analysis) {
  const lines = [`素材摘要：${analysis.summary || "暂无"}`];
  if (analysis.opportunities?.length) {
    lines.push("", "可拍机会：");
    analysis.opportunities.forEach((item) => lines.push(`- ${item}`));
  }
  if (analysis.risks?.length) {
    lines.push("", "注意事项：");
    analysis.risks.forEach((item) => lines.push(`- ${item}`));
  }
  if (analysis.model) {
    lines.push("", `生成方式：${analysis.model}`);
    el.provider.textContent = `模型：${analysis.model}`;
  }
  if (analysis.model_error) {
    lines.push("", `模型调用失败，已使用本地规则：${analysis.model_error}`);
  }
  el.analysis.textContent = lines.join("\n");
}

function renderQuestion(question) {
  if (!question) {
    el.questionBox.innerHTML = `
      <p class="question-title">引导信息已完成</p>
      <p class="muted">现在可以生成选题。你也可以回到第一步修改素材后重新开始。</p>
    `;
    return;
  }
  el.questionBox.innerHTML = `
    <p class="question-title">${question.label}</p>
    <p>${question.question}</p>
    <input id="answerInput" placeholder="${question.placeholder}" />
    <button id="answerBtn">保存并继续</button>
  `;
  document.querySelector("#answerBtn").addEventListener("click", async () => {
    const input = document.querySelector("#answerInput");
    const answer = input.value.trim();
    if (!answer) {
      toast("先填一下这一项");
      return;
    }
    try {
      setBusy(document.querySelector("#answerBtn"), true, "保存中");
      const result = await api(`/api/projects/${state.projectId}/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: question.id, answer }),
      });
      renderQuestion(result.next);
      updateStep(result.next ? "questions" : "topics");
    } catch (error) {
      toast(error.message);
      setBusy(document.querySelector("#answerBtn"), false);
    }
  });
}

function renderTopics(topics) {
  el.topics.innerHTML = "";
  topics.forEach((topic, index) => {
    const card = document.createElement("article");
    card.className = "topic-card";
    card.innerHTML = `
      <div class="tag-row">
        <span class="tag">${topic.angle || "选题"}</span>
        <span class="tag">${topic.style || "短视频"}</span>
      </div>
      <h3>${topic.title}</h3>
      <p>${topic.reason || ""}</p>
      <p class="muted">目标：${topic.goal || "提升内容效果"}</p>
      <button>生成脚本 ${String(index + 1).padStart(2, "0")}</button>
    `;
    card.querySelector("button").addEventListener("click", () => {
      document.querySelectorAll(".topic-card").forEach((item) => item.classList.remove("selected"));
      card.classList.add("selected");
      generateScript(topic);
    });
    el.topics.appendChild(card);
  });
}

async function createProject() {
  const text = el.idea.value.trim();
  if (!text && state.pendingFiles.length === 0) {
    throw new Error("先输入一段想法，或上传图片/视频");
  }
  const project = await api("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  state.projectId = project.id;
  for (const file of state.pendingFiles) {
    const form = new FormData();
    form.append("file", file);
    await api(`/api/projects/${state.projectId}/assets`, {
      method: "POST",
      body: form,
    });
  }
}

async function start() {
  try {
    setBusy(el.startBtn, true, "解析中");
    updateStep("analysis");
    await createProject();
    const thinking = runThinking("正在理解素材", [
      "读取你的文字和上传素材...",
      "提取可拍摄的内容线索...",
      "判断适合的短视频表达方向...",
      "整理下一步需要追问的问题...",
    ]);
    const [analysis] = await Promise.all([
      api(`/api/projects/${state.projectId}/analyze`, { method: "POST" }),
      thinking,
    ]);
    await finishThinking("素材理解完成");
    renderAnalysis(analysis);
    const next = await api(`/api/projects/${state.projectId}/questions/next`);
    renderQuestion(next.question);
    updateStep("questions");
    toast("素材分析完成");
  } catch (error) {
    el.thinking.classList.add("hidden");
    toast(error.message);
  } finally {
    setBusy(el.startBtn, false);
  }
}

async function generateTopics() {
  if (!state.projectId) {
    toast("先完成素材分析");
    return;
  }
  try {
    setBusy(el.topicBtn, true, "生成中");
    updateStep("topics");
    const thinking = runThinking("正在生成选题", [
      "复盘素材里的冲突点和卖点...",
      "匹配目标用户的兴趣入口...",
      "生成不同内容角度...",
      "筛选更适合拍摄的选题...",
    ]);
    const [result] = await Promise.all([
      api(`/api/projects/${state.projectId}/topics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: 6 }),
      }),
      thinking,
    ]);
    await finishThinking("选题已生成");
    renderTopics(result.topics);
    el.topicHint.textContent = `已生成 ${result.topics.length} 个选题`;
  } catch (error) {
    el.thinking.classList.add("hidden");
    toast(error.message);
  } finally {
    setBusy(el.topicBtn, false);
  }
}

async function generateScript(topic) {
  try {
    state.selectedTopic = topic;
    el.scriptStatus.textContent = "生成中";
    el.script.textContent = "正在生成脚本...";
    updateStep("script");
    const thinking = runThinking("正在组织拍摄脚本", [
      "拆解选题的开头钩子...",
      "规划 30 秒分镜节奏...",
      "生成口播和画面建议...",
      "补充拍摄提醒和封面方向...",
    ], 2300);
    const [result] = await Promise.all([
      api(`/api/projects/${state.projectId}/scripts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      }),
      thinking,
    ]);
    await finishThinking("脚本已完成");
    state.scriptMarkdown = result.script.markdown || "";
    el.script.textContent = state.scriptMarkdown || JSON.stringify(result.script, null, 2);
    el.scriptStatus.textContent = "已生成";
    toast("脚本已生成");
  } catch (error) {
    el.thinking.classList.add("hidden");
    el.script.textContent = "脚本生成失败。";
    el.scriptStatus.textContent = "失败";
    toast(error.message);
  }
}

el.asset.addEventListener("change", () => {
  state.pendingFiles = Array.from(el.asset.files || []);
  renderAssets();
});

el.startBtn.addEventListener("click", start);
el.topicBtn.addEventListener("click", generateTopics);

el.copyBtn.addEventListener("click", async () => {
  if (!state.scriptMarkdown) {
    toast("还没有脚本可复制");
    return;
  }
  await navigator.clipboard.writeText(state.scriptMarkdown);
  toast("脚本已复制");
});

el.downloadBtn.addEventListener("click", () => {
  if (!state.scriptMarkdown) {
    toast("还没有脚本可下载");
    return;
  }
  const blob = new Blob([state.scriptMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "short-video-script.md";
  link.click();
  URL.revokeObjectURL(url);
});

loadModelStatus();
