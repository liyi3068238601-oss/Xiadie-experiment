// CYR.2C taskworkbench UI prototype interactions
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// viewport switch
$$(".viewport-switch button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".viewport-switch button").forEach((b) => b.classList.toggle("active", b === btn));
    $(".app-window").dataset.viewport = btn.dataset.viewport;
  });
});

// navigation
const navButtons = $$(".main-nav button");
const switchView = (view) => {
  navButtons.forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".screen").forEach((s) => s.classList.toggle("active", s.id === `screen-${view}`));
};
navButtons.forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));
$$(".recent-list button[data-view]").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));

// ---- chat plan card states ----
const planCard = $("#plan-card");
const planState = (state) => {
  planCard.dataset.state = state;
  const pill = $("#plan-status-pill");
  const nodes = $("#plan-nodes");
  const moreBtn = $("#more-nodes");
  const note = $(".plan-note");
  if (state === "loading") {
    pill.textContent = "生成中";
    if (!$(".skeleton")) {
      const sk = document.createElement("div");
      sk.className = "skeleton";
      sk.innerHTML = "<i></i><i></i><i></i>";
      nodes.after(sk);
    }
    note.textContent = "遐蝶正在整理步骤…";
  } else {
    $(".skeleton")?.remove();
    if (state === "pending") {
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
    } else {
      nodes.style.display = "";
      moreBtn.style.display = "";
      note.textContent = "确认后创建任务草稿，不会自动开始执行";
    }
  }
};
planState("pending");
$$(".plan-state-switch button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".plan-state-switch button").forEach((b) => b.classList.toggle("active", b === btn));
    planState(btn.dataset.planState);
  });
});
$("#plan-enter").addEventListener("click", () => switchView("workbench"));
$("#plan-cancel").addEventListener("click", () => planState("cancelled"));

// ---- workbench states ----
const nodeList = $("#node-list");
const invalidBanner = $("#invalid-banner");
const wbState = (state) => {
  invalidBanner.hidden = state !== "invalid";
  nodeList.style.display = "none";
  $(".wb-skeleton")?.remove();
  $("#replan-modal").hidden = true;
  if (state === "replanning") {
    const sk = document.createElement("div");
    sk.className = "wb-skeleton";
    sk.innerHTML = "<i></i><i></i><i></i>";
    nodeList.after(sk);
    $(".editor-head .muted").textContent = "正在生成候选计划…";
  } else if (state === "replan-failed") {
    invalidBanner.hidden = false;
    invalidBanner.querySelector("strong").textContent = "候选计划生成失败";
    invalidBanner.querySelector("p").textContent = "程序校验未通过：未锁定节点依赖被移除。请调整目标后重试。";
    invalidBanner.querySelector(".ghost").textContent = "重试";
    $(".editor-head .muted").textContent = "生成失败，当前计划未改变";
  } else {
    nodeList.style.display = "grid";
    invalidBanner.querySelector("strong").textContent = "有节点引用已失效，无法开始执行";
    invalidBanner.querySelector("p").textContent = "请移除失效引用，或重新生成计划。";
    invalidBanner.querySelector(".ghost").textContent = "处理失效引用";
    $(".editor-head .muted").textContent = "保存前修改不会生效 · 批准只批准当前计划";
  }
};
wbState("normal");
$$(".wb-state-switch button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".wb-state-switch button").forEach((b) => b.classList.toggle("active", b === btn));
    wbState(btn.dataset.wbState);
  });
});
$("#wb-replan").addEventListener("click", () => { $("#replan-modal").hidden = false; });
$("#modal-close").addEventListener("click", () => { $("#replan-modal").hidden = true; });
$("#modal-cancel").addEventListener("click", () => { $("#replan-modal").hidden = true; });
$("#modal-confirm").addEventListener("click", () => {
  $("#replan-modal").hidden = true;
  $$(".wb-state-switch button").forEach((b) => b.classList.toggle("active", b.dataset.wbState === "replanning"));
  wbState("replanning");
  setTimeout(() => {
    $$(".wb-state-switch button").forEach((b) => b.classList.toggle("active", b.dataset.wbState === "normal"));
    wbState("normal");
  }, 1400);
});

// lock toggles on node cards
$$(".node-card .lock-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const card = btn.closest(".node-card");
    const locked = card.dataset.lock !== "none";
    if (locked) {
      card.dataset.lock = "none";
      btn.querySelector("svg use").setAttribute("href", "#i-unlock");
      btn.setAttribute("aria-label", "锁定节点");
      card.querySelector(".lock-pill")?.remove();
    } else {
      card.dataset.lock = "explicit";
      btn.querySelector("svg use").setAttribute("href", "#i-lock");
      btn.setAttribute("aria-label", "解锁节点");
      if (!card.querySelector(".lock-pill")) {
        const pill = document.createElement("span");
        pill.className = "status-pill lock-pill";
        pill.textContent = "已锁定";
        card.querySelector("header strong").after(pill);
      }
    }
  });
});

// ---- recovery states ----
const recoveryCard = $("#recovery-card");
const recoveryState = (state) => {
  recoveryCard.dataset.mode = state === "empty" ? "empty" : "data";
  const risk = $("#recovery-risk");
  const title = $("#recovery-title");
  const retry = $("#act-retry");
  const continueBtn = $("#act-continue");
  const evidence = $("#recovery-evidence");
  const pill = $("#recovery-state-pill");
  $(".empty-copy")?.remove();
  risk.className = "risk-pill";
  retry.disabled = false; continueBtn.disabled = false;
  if (state === "free") {
    risk.classList.add("low"); risk.textContent = "风险 · 低";
    title.textContent = "最后一次工具操作无副作用，可安全继续或重试";
    pill.textContent = "paused · side_effect_free";
  } else if (state === "idempotent") {
    risk.classList.add("mid"); risk.textContent = "风险 · 中";
    title.textContent = "重试安全，但需确认输入未变化";
    retry.textContent = "重试（还剩 2 次）";
    pill.textContent = "paused · idempotent";
  } else if (state === "effectful") {
    risk.classList.add("high"); risk.textContent = "风险 · 高";
    title.textContent = "有副作用操作，继续前需要确认";
    retry.disabled = true; retry.textContent = "重试（不可用）";
    continueBtn.textContent = "继续（需确认）";
    pill.textContent = "paused · side_effectful";
  } else if (state === "no-evidence") {
    risk.classList.add("none"); risk.textContent = "无证据 · fail closed";
    title.textContent = "没有可用的工具终态证据，只允许重新规划";
    continueBtn.disabled = true; retry.disabled = true;
    continueBtn.textContent = "继续（不可用）"; retry.textContent = "重试（不可用）";
    pill.textContent = "failed · no evidence";
  } else if (state === "empty") {
    risk.classList.add("none"); risk.textContent = "—";
    title.textContent = "暂无工具执行记录";
    evidence.style.display = "none";
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "当前运行没有工具执行记录；接入工具后将在这里显示恢复建议。";
    evidence.after(empty);
    pill.textContent = "paused";
  } else {
    risk.classList.add("mid"); risk.textContent = "风险 · 中";
    title.textContent = "基于最后一次工具证据";
    retry.textContent = "重试（还剩 2 次）"; continueBtn.textContent = "继续";
    evidence.style.display = "";
    pill.textContent = "paused · idempotent";
  }
};
recoveryState("idempotent");
$$(".recovery-state-switch button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".recovery-state-switch button").forEach((b) => b.classList.toggle("active", b === btn));
    recoveryState(btn.dataset.recState);
  });
});
$("#act-replan").addEventListener("click", () => switchView("workbench"));
