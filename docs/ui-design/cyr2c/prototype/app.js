// CYR.2C 任务工作台 UI 原型（基于当前 UI）交互
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// 预览尺寸
$$(".viewport-switch button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".viewport-switch button").forEach((b) => b.classList.toggle("active", b === btn));
    $(".app-window").dataset.viewport = btn.dataset.viewport;
  });
});

// 导航
const navButtons = $$(".nav button");
const switchView = (view) => {
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".screen").forEach((s) => s.classList.toggle("active", s.id === `screen-${view}`));
};
navButtons.forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));

// ---- 聊天计划卡状态 ----
const planCard = $("#plan-card");
const planState = (state) => {
  planCard.dataset.state = state;
  const pill = $("#plan-status-pill");
  const nodes = $("#plan-nodes");
  const moreBtn = $("#more-nodes");
  const note = $("#plan-note");
  $(".plan-skeleton")?.remove();
  nodes.style.display = "";
  moreBtn.style.display = "";
  if (state === "loading") {
    pill.textContent = "生成中";
    const sk = document.createElement("div");
    sk.className = "plan-skeleton";
    sk.innerHTML = "<i></i><i></i><i></i>";
    nodes.after(sk);
    note.textContent = "遐蝶正在整理步骤…";
  } else if (state === "pending") {
    pill.textContent = "待确认";
    note.textContent = "确认后创建任务草稿，不会自动开始执行";
  } else if (state === "editing") {
    pill.textContent = "编辑中";
    nodes.style.display = "none";
    moreBtn.style.display = "none";
    note.textContent = "计划已进入工作台编辑中";
  } else if (state === "failed") {
    pill.textContent = "生成失败";
    nodes.style.display = "none";
    moreBtn.style.display = "none";
    note.innerHTML = '<span class="plan-fail"><svg><use href="#i-alert"/></svg>候选计划未通过校验：引用 3 来源已失效。可调整目标后重试。</span>';
  } else if (state === "cancelled") {
    pill.textContent = "已取消";
    nodes.style.display = "none";
    moreBtn.style.display = "none";
    note.textContent = "已放弃该计划";
  }
};
planState("pending");
$$(".demo-bar[data-plan-state]").length ||
  $$("#screen-chat .demo-bar button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#screen-chat .demo-bar button").forEach((b) => b.classList.toggle("active", b === btn));
      planState(btn.dataset.planState);
    });
  });
$("#plan-enter").addEventListener("click", () => switchView("tasks"));
$("#plan-cancel").addEventListener("click", () => planState("cancelled"));

// ---- 工作台状态 ----
const runPanel = $("#run-panel");
const invalidBanner = $("#invalid-banner");
const skeleton = $("#wb-skeleton");
const editor = $("#plan-editor");
const nodeIds = ["#node-1", "#node-2", "#node-3"];
const setNodesVisible = (visible) => nodeIds.forEach((id) => { const el = $(id); if (el) el.style.display = visible ? "" : "none"; });
const wbState = (state) => {
  invalidBanner.hidden = true;
  skeleton.hidden = true;
  setNodesVisible(true);
  $("#replan-modal").hidden = true;
  if (state === "replanning") {
    setNodesVisible(false);
    skeleton.hidden = false;
  } else if (state === "replan-failed") {
    invalidBanner.hidden = false;
    invalidBanner.querySelector("strong").textContent = "候选计划生成失败";
    invalidBanner.querySelector("p").textContent = "程序校验未通过：未锁定节点依赖被移除。请调整目标后重试。";
    invalidBanner.querySelector("button").textContent = "重试";
  } else if (state === "invalid") {
    invalidBanner.hidden = false;
    invalidBanner.querySelector("strong").textContent = "有节点引用已失效，无法开始执行";
    invalidBanner.querySelector("p").textContent = "请移除失效引用，或重新生成计划。";
    invalidBanner.querySelector("button").textContent = "处理失效引用";
  }
};
wbState("normal");
$$("#screen-tasks .demo-bar button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#screen-tasks .demo-bar button").forEach((b) => b.classList.toggle("active", b === btn));
    wbState(btn.dataset.wbState);
  });
});
$("#wb-replan").addEventListener("click", () => { $("#replan-modal").hidden = false; });
$("#modal-close").addEventListener("click", () => { $("#replan-modal").hidden = true; });
$("#modal-cancel").addEventListener("click", () => { $("#replan-modal").hidden = true; });
$("#modal-confirm").addEventListener("click", () => {
  $("#replan-modal").hidden = true;
  $$("#screen-tasks .demo-bar button").forEach((b) => b.classList.toggle("active", b.dataset.wbState === "replanning"));
  wbState("replanning");
  setTimeout(() => {
    $$("#screen-tasks .demo-bar button").forEach((b) => b.classList.toggle("active", b.dataset.wbState === "normal"));
    wbState("normal");
  }, 1400);
});
$("#wb-edit-plan").addEventListener("click", () => { editor.hidden = false; });
$("#editor-close").addEventListener("click", () => { editor.hidden = true; });
$("#invalid-focus").addEventListener("click", () => {
  const node = $("#node-2");
  if (!node) return;
  node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.style.outline = "1px solid var(--danger)";
  setTimeout(() => { node.style.outline = ""; }, 1600);
});

// 锁定切换（运行面板节点与计划编辑器节点共用）
const bindLock = (btn) => {
  btn.addEventListener("click", () => {
    const card = btn.closest(".task-node, .task-plan-node");
    if (!card) return;
    const locked = card.dataset.lock !== "none";
    const icon = btn.querySelector("svg use");
    if (locked) {
      card.dataset.lock = "none";
      icon.setAttribute("href", "#i-unlock");
      btn.setAttribute("aria-label", "锁定节点");
      card.querySelector(".node-lock-pill")?.remove();
    } else {
      card.dataset.lock = "explicit";
      icon.setAttribute("href", "#i-lock");
      btn.setAttribute("aria-label", "解锁节点");
      if (!card.querySelector(".node-lock-pill")) {
        const pill = document.createElement("span");
        pill.className = "node-lock-pill";
        pill.textContent = "已锁定";
        const title = card.querySelector(".node-main strong") || card.querySelector("b");
        if (title) title.after(pill);
        else card.querySelector("div > b")?.after(pill);
      }
    }
  });
};
$$(".node-lock-btn").forEach(bindLock);

// ---- 恢复面板状态 ----
const recoveryCard = $("#recovery-card");
const recoveryState = (state) => {
  recoveryCard.dataset.mode = state === "empty" ? "empty" : "data";
  const risk = $("#recovery-risk");
  const title = $("#recovery-title");
  const retry = $("#act-retry");
  const cont = $("#act-continue");
  const evidence = $("#recovery-evidence");
  const empty = $("#recovery-empty");
  const pill = $("#recovery-state-pill");
  risk.className = "risk-pill";
  retry.disabled = false; cont.disabled = false;
  evidence.style.display = ""; empty.hidden = true;
  if (state === "free") {
    risk.classList.add("low"); risk.textContent = "风险 · 低";
    title.textContent = "最后一次工具操作无副作用，可安全继续或重试";
    retry.textContent = "重试"; cont.textContent = "继续";
    pill.textContent = "paused · side_effect_free";
  } else if (state === "idempotent") {
    risk.classList.add("mid"); risk.textContent = "风险 · 中";
    title.textContent = "重试安全，但需确认输入未变化";
    retry.textContent = "重试（还剩 2 次）"; cont.textContent = "继续";
    pill.textContent = "paused · idempotent";
  } else if (state === "effectful") {
    risk.classList.add("high"); risk.textContent = "风险 · 高";
    title.textContent = "有副作用操作，继续前需要确认";
    retry.disabled = true; retry.textContent = "重试（不可用）";
    cont.textContent = "继续（需确认）";
    pill.textContent = "paused · side_effectful";
  } else if (state === "no-evidence") {
    risk.classList.add("none"); risk.textContent = "无证据 · fail closed";
    title.textContent = "没有可用的工具终态证据，只允许重新规划";
    cont.disabled = true; retry.disabled = true;
    cont.textContent = "继续（不可用）"; retry.textContent = "重试（不可用）";
    pill.textContent = "failed · no evidence";
  } else if (state === "empty") {
    risk.classList.add("none"); risk.textContent = "—";
    title.textContent = "暂无工具执行记录";
    evidence.style.display = "none"; empty.hidden = false;
    pill.textContent = "paused";
  }
};
recoveryState("idempotent");
$$("#screen-recovery .demo-bar button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("#screen-recovery .demo-bar button").forEach((b) => b.classList.toggle("active", b === btn));
    recoveryState(btn.dataset.recState);
  });
});
$("#act-replan").addEventListener("click", () => switchView("tasks"));
