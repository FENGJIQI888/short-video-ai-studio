const el = {
  todayRevenue: document.querySelector("#todayRevenue"),
  dailyGoal: document.querySelector("#dailyGoal"),
  goalStatus: document.querySelector("#goalStatus"),
  goalGap: document.querySelector("#goalGap"),
  todayOrders: document.querySelector("#todayOrders"),
  totalOrders: document.querySelector("#totalOrders"),
  statusCounts: document.querySelector("#statusCounts"),
  orders: document.querySelector("#orders"),
  refreshBtn: document.querySelector("#refreshBtn"),
  copyDailyScriptBtn: document.querySelector("#copyDailyScriptBtn"),
  toast: document.querySelector("#toast"),
};

function yuan(cents) {
  return `¥${Math.round((cents || 0) / 100)}`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function toast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  window.setTimeout(() => el.toast.classList.remove("show"), 2200);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = response.statusText || "请求失败";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep fallback message.
    }
    throw new Error(message);
  }
  return response.json();
}

async function copyText(text) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

function renderSummary(summary) {
  const goal = summary.daily_goal_cents || 2000;
  const revenue = summary.today_revenue_cents || 0;
  const gap = Math.max(0, goal - revenue);
  el.todayRevenue.textContent = yuan(revenue);
  el.dailyGoal.textContent = yuan(goal);
  el.goalStatus.textContent = summary.today_goal_met ? "今日已达标" : "继续找客户";
  el.goalGap.textContent = summary.today_goal_met ? "可以追月费升级" : `还差 ${yuan(gap)}`;
  el.todayOrders.textContent = String(summary.today_order_count || 0);
  el.totalOrders.textContent = String(summary.total_order_count || 0);
  const counts = summary.status_counts || {};
  el.statusCounts.textContent = `new ${counts.new || 0} / paid ${counts.paid || 0} / delivered ${counts.delivered || 0}`;
}

function statusLabel(status) {
  return {
    new: "待跟进",
    paid: "已付款",
    delivered: "已交付",
    cancelled: "已取消",
  }[status] || status;
}

function nextAction(order) {
  if (order.status === "new") return "先确认付款，再开始生成内容。";
  if (order.status === "paid") return "今天必须交付，交付后追问是否升级月包。";
  if (order.status === "delivered") return "跟进结果，尝试卖 ¥199/月内容包。";
  return "如客户重新激活，再改回待跟进。";
}

function orderMessage(order) {
  return [
    `${order.name || "老板"}，你的 ¥20 短视频试跑需求我已经收到。`,
    `我会基于你提供的素材方向「${order.material || "素材"}」整理：`,
    "1. 3 个适合拍摄的选题",
    "2. 1 条可直接拍的脚本",
    "3. 5 个标题/开头钩子",
    "确认付款后我就开始处理，做好后直接发你。",
  ].join("\n");
}

function renderOrders(orders) {
  if (!orders.length) {
    el.orders.innerHTML = `
      <article class="empty-card">
        <strong>暂无订单</strong>
        <p>先去找 20 个潜在客户，把首页的试跑入口发出去。</p>
      </article>
    `;
    return;
  }
  el.orders.innerHTML = orders.map((order) => `
    <article class="order-card" data-order-id="${escapeHtml(order.id)}">
      <div class="order-top">
        <div>
          <span class="tag">${escapeHtml(statusLabel(order.status))}</span>
          <span class="tag">${escapeHtml(order.platform || "未填平台")}</span>
        </div>
        <strong>${yuan(order.amount_cents)}</strong>
      </div>
      <h3>${escapeHtml(order.business || "未填行业")} · ${escapeHtml(order.contact)}</h3>
      <p>${escapeHtml(order.material)}</p>
      <p class="muted">订单号：${escapeHtml(order.id)} · ${escapeHtml(order.created_at)}</p>
      <p class="muted">${escapeHtml(nextAction(order))}</p>
      <div class="order-actions">
        <button data-action="paid">标记已付款</button>
        <button data-action="delivered">标记已交付</button>
        <button data-action="copy">复制跟进话术</button>
        <button data-action="cancelled">取消</button>
      </div>
    </article>
  `).join("");
}

async function loadDashboard() {
  const [summary, orderResult] = await Promise.all([
    api("/api/revenue-summary"),
    api("/api/trial-orders?limit=100"),
  ]);
  renderSummary(summary);
  renderOrders(orderResult.orders || []);
}

async function updateOrderStatus(orderId, status) {
  await api(`/api/trial-orders/${orderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  toast("订单状态已更新");
  await loadDashboard();
}

el.orders.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  const card = event.target.closest(".order-card");
  if (!button || !card) return;
  const orderId = card.dataset.orderId;
  const action = button.dataset.action;
  if (action === "copy") {
    const order = (await api("/api/trial-orders?limit=100")).orders.find((item) => item.id === orderId);
    await copyText(orderMessage(order || {}));
    toast("跟进话术已复制");
    return;
  }
  await updateOrderStatus(orderId, action);
});

el.refreshBtn.addEventListener("click", () => {
  loadDashboard().then(() => toast("已刷新")).catch((error) => toast(error.message));
});

el.copyDailyScriptBtn.addEventListener("click", async () => {
  await copyText([
    "老板，我在做一个 ¥20 短视频试跑。",
    "你发我一张图、一段视频或者一句想法，我给你出：3 个选题、1 条可拍脚本、5 个标题钩子。",
    "适合餐饮、美业、健身、民宿、探店和本地服务账号。要不要我先帮你试一版？",
  ].join("\n"));
  toast("今日获客话术已复制");
});

loadDashboard().catch((error) => toast(error.message));
