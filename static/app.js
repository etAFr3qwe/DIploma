const state = {
  users: [],
  courses: [],
  selectedUserId: null,
  isLoggedIn: true,
  currentAttempt: null,
  currentAttemptId: null,
  currentTaskId: null,
  timerInterval: null,
  timerStartedAt: null,
  chatBound: false,
  teacherPanelBound: false,
  teacherStatusTab: "",
  solutionFiles: [],
  solutionFileUrls: [],
};

const MAX_SOLUTION_FILES = 10;
const MAX_SOLUTION_FILE_SIZE = 10 * 1024 * 1024;
const SOLUTION_FILE_PATTERN = /\.(jpe?g|png|pdf)$/i;

const ACTIVE_ATTEMPT_KEYS = {
  attemptId: "currentAttemptId",
  taskId: "currentTaskId",
  startedAt: "startedAt",
};

document.addEventListener("DOMContentLoaded", async () => {
  bindCommonActions();
  await loadUsers();

  const page = document.body.dataset.page || "home";
  if (page === "home") {
    await initHomePage();
  }
  if (page === "courses") {
    await initCoursesPage();
  }
  if (page === "course") {
    await initCoursePage();
  }
  if (page === "section") {
    await initSectionPage();
  }
  if (page === "task") {
    await initTaskPage();
  }
  if (page === "teacher-attempts") {
    await initTeacherAttemptsPage();
  }
  if (page === "teacher-attempt-detail") {
    await initTeacherAttemptDetailPage();
  }
});

function bindCommonActions() {
  const modalClose = document.getElementById("modal-close");
  if (modalClose) {
    modalClose.addEventListener("click", () => closeModal());
  }

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  document.getElementById("image-modal-close")?.addEventListener("click", closeImageModal);

  document.getElementById("train-button")?.addEventListener("click", async () => {
    const result = await api("/train", { method: "POST" });
    showModal(
      "Переобучение модели",
      `Модель обновлена. Обучающих примеров: ${result.samples || 0}. Точность: ${formatPercent(result.accuracy)}.`
    );
  });

  document.getElementById("create-pool-button")?.addEventListener("click", createWeeklyPool);

  document.getElementById("login-button")?.addEventListener("click", () => {
    state.isLoggedIn = true;
    localStorage.setItem("exam_platform_logged_in", "true");
    renderAuthState();
    updateHomeActionLinks();
    showModal("Вход выполнен", `Вы вошли как ${escapeHtml(activeUser()?.name || "тестовый пользователь")}.`);
  });

  document.getElementById("logout-button")?.addEventListener("click", () => {
    state.isLoggedIn = false;
    localStorage.setItem("exam_platform_logged_in", "false");
    renderAuthState();
    showModal("Выход выполнен", "Личные разделы снова станут доступны после входа.");
  });

  document.querySelectorAll('[data-nav-item="logout"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      state.isLoggedIn = false;
      localStorage.setItem("exam_platform_logged_in", "false");
      renderAuthState();
      location.href = "/";
    });
  });
}

async function api(url, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = {
    Accept: "application/json",
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let message = `Ошибка запроса: ${response.status}`;
    if (contentType.includes("application/json")) {
      const errorBody = await response.json().catch(() => null);
      if (typeof errorBody?.detail === "string") {
        message = errorBody.detail;
      } else if (Array.isArray(errorBody?.detail)) {
        message = errorBody.detail.map((item) => item.msg || item.message || "Проверьте данные формы.").join(" ");
      }
    } else {
      message = (await response.text()) || message;
    }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

async function loadUsers() {
  state.users = await api("/users");
  const urlUserId = Number(new URLSearchParams(location.search).get("user_id")) || Number(document.body.dataset.currentUserId) || null;
  state.isLoggedIn = urlUserId ? true : localStorage.getItem("exam_platform_logged_in") !== "false";
  const students = state.users.filter((user) => isStudent(user));
  const defaultUser = students[0] || state.users[0];
  state.selectedUserId = urlUserId || Number(localStorage.getItem("exam_platform_user_id")) || defaultUser?.id || null;
  if (state.selectedUserId) {
    localStorage.setItem("exam_platform_user_id", String(state.selectedUserId));
  }
  if (urlUserId) {
    localStorage.setItem("exam_platform_logged_in", "true");
  }

  document.querySelectorAll("#user-select").forEach((select) => {
    select.innerHTML = state.users
      .map((user) => `<option value="${user.id}">${escapeHtml(user.name)} · ${roleLabel(user.role)}</option>`)
      .join("");
    if (state.selectedUserId) {
      select.value = String(state.selectedUserId);
    }
    select.addEventListener("change", async (event) => {
      state.selectedUserId = Number(event.target.value);
      localStorage.setItem("exam_platform_user_id", String(state.selectedUserId));
      state.isLoggedIn = true;
      localStorage.setItem("exam_platform_logged_in", "true");
      await refreshCurrentPage();
    });
  });

  renderActiveUser();
  renderAuthState();
  renderNavigationState();
}

async function refreshCurrentPage() {
  renderActiveUser();
  const page = document.body.dataset.page || "home";
  if (page === "home") {
    await initHomePage();
  }
  if (page === "courses") {
    await initCoursesPage();
  }
  if (page === "course") {
    await initCoursePage(false);
  }
  if (page === "section") {
    await initSectionPage(false);
  }
  if (page === "task") {
    await initTaskPage(false);
  }
  if (page === "teacher-attempts") {
    await ensureProtectedPageRole(["teacher", "admin"], "/");
    await initTeacherAttemptsPage();
  }
  if (page === "teacher-attempt-detail") {
    await ensureProtectedPageRole(["teacher", "admin"], "/");
    await initTeacherAttemptDetailPage();
  }
  if (["parent-report", "parent-progress"].includes(page)) {
    await ensureProtectedPageRole(["parent", "admin"], "/");
  }
  if (["admin-dashboard", "admin-users"].includes(page)) {
    await ensureProtectedPageRole(["admin"], "/");
  }
}

function activeUser() {
  return state.users.find((user) => user.id === state.selectedUserId) || state.users[0];
}

function activeUserId() {
  return activeUser()?.id || 1;
}

function isStudent(user) {
  return roleKey(user) === "student";
}

function roleKey(userOrRole) {
  const raw = typeof userOrRole === "string" ? userOrRole : userOrRole?.role;
  const role = String(raw || "").trim().toLowerCase();
  const aliases = {
    student: "student",
    "ученик": "student",
    teacher: "teacher",
    "преподаватель": "teacher",
    parent: "parent",
    "родитель": "parent",
    admin: "admin",
    "администратор": "admin",
  };
  return aliases[role] || role;
}

function roleLabel(role) {
  const map = {
    student: "ученик",
    teacher: "преподаватель",
    parent: "родитель",
    admin: "администратор",
  };
  return map[roleKey(role)] || "роль не указана";
}

function currentPoolTaskId() {
  const value = new URLSearchParams(location.search).get("pool_task_id");
  return value ? Number(value) : null;
}

function renderActiveUser() {
  const user = activeUser();
  if (!user) return;

  setText("profile-name", user.name);
  setText(
    "profile-meta",
    `${roleLabel(user.role)} · ${user.grade || "класс не указан"} · ${user.target_exam || "экзамен не выбран"} · ${user.goal || "цель уточняется"}`
  );
}

function renderAuthState() {
  setText("auth-status", state.isLoggedIn ? "Вход выполнен" : "Вы вышли из учебного профиля");
  const loginButton = document.getElementById("login-button");
  const logoutButton = document.getElementById("logout-button");
  if (loginButton) loginButton.disabled = state.isLoggedIn;
  if (logoutButton) logoutButton.disabled = !state.isLoggedIn;
  renderNavigationState();
  renderHomeActionVisibility();
}

function renderNavigationState() {
  const nav = document.getElementById("main-nav");
  if (!nav) return;

  const role = state.isLoggedIn ? roleKey(activeUser()) : "guest";
  const activePage = resolveActiveNavPage(nav.dataset.activePage || document.body.dataset.page || "home");
  const userId = activeUserId();
  const urls = {
    home: "/",
    courses: state.isLoggedIn ? `/courses?user_id=${userId}` : "/courses",
    plan: `/student/plan?user_id=${userId}`,
    analytics: `/student/analytics?user_id=${userId}`,
    forecast: `/student/forecast?user_id=${userId}`,
    tutor: `/tutor?user_id=${userId}`,
    parent_report: `/parent/report?user_id=${userId}`,
    parent_progress: `/parent/progress?user_id=${userId}`,
    teacher: `/teacher?user_id=${userId}`,
    teacher_attempts: `/teacher/attempts?user_id=${userId}`,
    admin_users: `/admin/users?user_id=${userId}`,
    admin_parent_reports: `/parent/report?user_id=${userId}`,
    admin_analytics: `/admin?user_id=${userId}#admin-analytics`,
    login: "/login",
    logout: "/",
  };

  nav.querySelectorAll("[data-nav-item]").forEach((link) => {
    const item = link.dataset.navItem || "";
    const roles = (link.dataset.navRoles || "").split(",").map((value) => value.trim()).filter(Boolean);
    const visible = roles.includes(role);
    link.hidden = !visible;
    if (urls[item]) {
      link.href = urls[item];
    }
    link.classList.toggle("active", item === activePage);
  });
}

function resolveActiveNavPage(defaultPage) {
  const page = document.body.dataset.page || "";
  const hash = location.hash.replace("#", "");
  if (page === "course") {
    const courseHashMap = {
      "weekly-plan": "plan",
      analytics: "analytics",
      forecast: "forecast",
      tutor: "tutor",
      "parent-report": "parent_report",
      "teacher-panel": "teacher",
    };
    return courseHashMap[hash] || "courses";
  }
  if (page === "task") {
    return "plan";
  }
  if (page === "section") {
    return "courses";
  }
  return defaultPage;
}

async function initHomePage() {
  state.courses = await api(`/courses?user_id=${activeUserId()}`);
  updateCourseNavLinks((courseForActiveUser() || state.courses[0])?.id);
  renderNavigationState();
  updateHomeActionLinks();
  renderHomeActionVisibility();
  renderHomeCourses(state.courses);
  bindHomeActions();
}

async function initCoursesPage() {
  state.courses = await api(`/courses?user_id=${activeUserId()}`);
  renderNavigationState();
  updateHomeActionLinks();
  renderHomeActionVisibility();
  renderHomeCourses(state.courses);
  bindHomeActions();
}

function updateCourseNavLinks(courseId) {
  if (!courseId) return;
  document.querySelectorAll('.main-nav a[href^="/courses/1"]').forEach((link) => {
    link.href = link.getAttribute("href").replace("/courses/1", `/courses/${courseId}`);
  });
}

function updateHomeActionLinks() {
  if (!state.courses.length) return;
  const ogeCourse = courseByExam("ОГЭ") || state.courses[0];
  const egeCourse = courseByExam("ЕГЭ") || state.courses[1] || state.courses[0];
  const activeCourse = courseForActiveUser() || ogeCourse;
  const urls = {
    startOge: `/courses/${ogeCourse.id}`,
    startEge: `/courses/${egeCourse.id}`,
    plan: `/student/plan?user_id=${activeUserId()}`,
    analytics: `/student/analytics?user_id=${activeUserId()}`,
    tutor: `/tutor?user_id=${activeUserId()}`,
    teacher: `/teacher?user_id=${activeUserId()}`,
    parent: `/parent/report?user_id=${activeUserId()}`,
  };
  document.querySelectorAll("[data-home-action]").forEach((link) => {
    const action = link.dataset.homeAction;
    if (urls[action]) link.setAttribute("href", urls[action]);
  });
}

function renderHomeActionVisibility() {
  const role = state.isLoggedIn ? roleKey(activeUser()) : "guest";
  const actionRoles = {
    startOge: new Set(["guest", "student", "teacher", "admin"]),
    startEge: new Set(["guest", "student", "teacher", "admin"]),
    plan: new Set(["student"]),
    analytics: new Set(["student"]),
    tutor: new Set(["student"]),
    teacher: new Set(["teacher", "admin"]),
    parent: new Set(["parent", "admin"]),
  };
  document.querySelectorAll("[data-home-action]").forEach((link) => {
    const action = link.dataset.homeAction;
    const allowed = actionRoles[action];
    link.hidden = Boolean(allowed && !allowed.has(role));
  });
}

function bindHomeActions() {
  document.querySelectorAll("[data-home-action], [data-requires-login]").forEach((link) => {
    if (link.dataset.boundHomeAction) return;
    link.addEventListener("click", (event) => {
      const action = link.dataset.homeAction;
      const access = action ? checkHomeActionAccess(action) : checkRoleAccess(link.dataset.requiresLogin);
      if (!access.allowed) {
        event.preventDefault();
        showModal(access.title, access.message);
      }
    });
    link.dataset.boundHomeAction = "true";
  });
}

function checkRoleAccess(requiredRole) {
  if (!requiredRole) return { allowed: true };
  if (!state.isLoggedIn) {
    return {
      allowed: false,
      title: "Нужен вход",
      message: "Выберите тестового пользователя и нажмите «Войти», чтобы открыть личные разделы.",
    };
  }
  const role = roleKey(activeUser());
  const allowed = requiredRole === "student" ? ["student", "admin"].includes(role) : role === requiredRole || role === "admin";
  return allowed
    ? { allowed: true }
    : {
        allowed: false,
        title: "Раздел недоступен для выбранной роли",
        message: `Сейчас выбран пользователь с ролью «${roleLabel(role)}». Выберите подходящую роль или администратора.`,
      };
}

async function ensureProtectedPageRole(allowedRoles, fallbackUrl = "/") {
  const role = roleKey(activeUser());
  if (!allowedRoles.includes(role)) {
    showModal("Раздел недоступен", `Сейчас выбран пользователь с ролью «${roleLabel(role)}».`);
    setTimeout(() => {
      location.href = fallbackUrl;
    }, 300);
  }
}

function checkHomeActionAccess(action) {
  const alwaysAllowed = new Set(["startOge", "startEge"]);
  if (alwaysAllowed.has(action)) {
    return { allowed: true };
  }
  if (!state.isLoggedIn) {
    return {
      allowed: false,
      title: "Нужен вход",
      message: "Выберите тестового пользователя и нажмите «Войти», чтобы открыть личные разделы.",
    };
  }

  const role = roleKey(activeUser());
  const allowedRoles = {
    plan: new Set(["student", "admin"]),
    analytics: new Set(["student", "admin"]),
    tutor: new Set(["student", "admin"]),
    teacher: new Set(["teacher", "admin"]),
    parent: new Set(["parent", "admin"]),
  };
  if (!allowedRoles[action] || allowedRoles[action].has(role)) {
    return { allowed: true };
  }
  return {
    allowed: false,
    title: "Раздел недоступен для выбранной роли",
    message: `Сейчас выбран пользователь с ролью «${roleLabel(role)}». Выберите подходящую роль или администратора.`,
  };
}

function courseByExam(examType) {
  return state.courses.find((course) => course.exam_type === examType);
}

function courseForActiveUser() {
  const user = activeUser();
  return courseByExam(user?.target_exam) || state.courses[0];
}

function renderHomeCourses(courses) {
  const grid = document.getElementById("home-course-grid");
  if (!grid) return;

  grid.innerHTML = courses
    .map((course) => {
      const moduleCount = course.section_count || course.sections?.length || 0;
      const taskCount = course.task_count || 0;
      const topicCount = course.topic_count || 0;
      const progress = Math.round(course.readiness_percent || 0);
      const predicted = Math.round(course.predicted_score || 0);

      return `
        <article class="course-card course-card-featured">
          <div class="course-card-top">
            <span class="badge">${escapeHtml(course.exam_type)}</span>
            <span class="muted">готовность ${progress}%</span>
          </div>
          <h3>${escapeHtml(course.title)}</h3>
          <p>${escapeHtml(course.description)}</p>
          <div class="metric-grid compact">
            <div><strong>${moduleCount}</strong><span>модулей</span></div>
            <div><strong>${topicCount}</strong><span>тем</span></div>
            <div><strong>${taskCount}</strong><span>заданий</span></div>
            <div><strong>${predicted}</strong><span>прогноз баллов</span></div>
          </div>
          <div class="progress-line" aria-label="Готовность ученика">
            <span style="width: ${progress}%"></span>
          </div>
          <div class="card-actions">
            <a class="button primary" href="/courses/${course.id}">Открыть курс</a>
            <a class="button ghost" href="/courses/${course.id}/plan?user_id=${activeUserId()}" data-requires-login="student">Перейти к плану</a>
            <a class="button ghost" href="/courses/${course.id}#modules">Начать подготовку</a>
          </div>
        </article>
      `;
    })
    .join("");
}

async function initCoursePage(rebindTabs = true) {
  const courseId = Number(document.body.dataset.courseId);
  const course = await api(`/courses/${courseId}?user_id=${activeUserId()}`);
  state.currentCourse = course;
  renderNavigationState();

  renderCourseHeader(course);
  renderCourseModules(course);
  if (rebindTabs) {
    bindCourseTabs();
  }
  applyCourseRoleVisibility();
  await renderWeeklyPlan(courseId);
  await renderCourseAttempts(courseId);
  await renderAnalytics(courseId);
  await renderTutorMaterials(course);
  const role = roleKey(activeUser());
  if (["parent", "admin"].includes(role)) {
    await renderParentReport();
  }
  if (["teacher", "admin"].includes(role)) {
    await renderTeacherDashboard();
  }
}

function applyCourseRoleVisibility() {
  const role = roleKey(activeUser());
  const teacherPanel = document.getElementById("teacher-panel");
  const parentReport = document.getElementById("parent-report");
  if (teacherPanel) teacherPanel.hidden = !["teacher", "admin"].includes(role);
  if (parentReport) parentReport.hidden = !["parent", "admin"].includes(role);
}

function renderCourseHeader(course) {
  setText("course-title", course.title);
  setText("course-description", course.description);
  setText("course-exam", course.exam_type);
  renderBreadcrumbs([
    { title: "Главная", href: "/" },
    { title: course.title },
  ]);

  const stats = document.getElementById("course-stats");
  if (stats) {
    stats.innerHTML = `
      ${metricItem("Общий прогресс", `${Math.round(course.readiness_percent || 0)}%`)}
      ${metricItem("Прогноз баллов", Math.round(course.predicted_score || 0))}
      ${metricItem("Выполнено заданий", course.completed_tasks || 0)}
      ${metricItem("Среднее время", formatDuration(course.average_time_seconds || 0))}
      ${metricItem("Верных ответов", `${Math.round(course.correct_percent || 0)}%`)}
    `;
  }
}

function renderCourseModules(course) {
  const grid = document.getElementById("module-grid");
  if (!grid) return;

  grid.innerHTML = (course.sections || [])
    .map((section) => {
      const progress = Math.round(section.completion_percent || 0);
      const average = Math.round(section.average_result_percent || 0);
      return `
        <article class="module-card">
          <div class="module-card-header">
            <span class="module-number">Модуль ${section.number}</span>
            <span class="status-pill ${progress === 100 ? "success" : "neutral"}">${progress}%</span>
          </div>
          <h3>${escapeHtml(section.title)}</h3>
          <p>${escapeHtml(section.description || "Раздел подготовки с теорией, примерами и заданиями.")}</p>
          <div class="module-facts">
            <span>${section.topic_count || 0} тем</span>
            <span>${section.task_count || 0} заданий</span>
            <span>средний результат ${average}%</span>
          </div>
          <div class="progress-line"><span style="width:${progress}%"></span></div>
          ${
            roleKey(activeUser()) === "admin"
              ? `<div class="admin-module-note">Эталоны решений редактируются внутри модуля, в карточках тем и заданий.</div>`
              : ""
          }
          <a class="button primary" href="/courses/${course.id}/sections/${section.id}">Открыть модуль</a>
        </article>
      `;
    })
    .join("");
}

function bindCourseTabs() {
  const tabs = document.querySelectorAll(".tab-button");
  const panels = document.querySelectorAll(".tab-panel");
  const activate = (tabName, updateHash = true) => {
    tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === tabName));
    panels.forEach((panel) => panel.classList.toggle("active", panel.id === tabName));
    if (updateHash) {
      history.replaceState(null, "", `#${tabName}`);
    }
    renderNavigationState();
  };

  tabs.forEach((button) => {
    button.addEventListener("click", () => activate(button.dataset.tab));
  });

  const validTabs = new Set(["modules", "weekly-plan", "attempts", "analytics", "tutor", "materials"]);
  const activateFromHash = () => {
    const hash = location.hash.replace("#", "");
    if (validTabs.has(hash)) {
      activate(hash, false);
    } else if (hash === "forecast") {
      activate("analytics", false);
    } else {
      activate("modules", false);
    }
  };
  window.addEventListener("hashchange", activateFromHash);
  activateFromHash();
}

async function renderWeeklyPlan(courseId) {
  const target = document.getElementById("weekly-plan-list");
  if (!target) return;

  const pools = await api(`/users/${activeUserId()}/assignment-pools`);
  const coursePools = pools.filter((pool) => pool.course_id === courseId);
  if (!coursePools.length) {
    target.innerHTML = `
      <div class="empty-card">
        <h3>План пока не назначен</h3>
        <p>Создайте недельный план, чтобы увидеть задания, дедлайны и статусы выполнения.</p>
      </div>
    `;
    return;
  }

  target.innerHTML = coursePools
    .map((pool) => {
      const progress = Math.round(pool.completion_percent || 0);
      const rows = (pool.pool_tasks || [])
        .map((item) => {
          const task = item.task || {};
          return `
            <tr>
              <td>
                <strong>${escapeHtml(task.title || "Задание")}</strong>
                <span class="cell-note">${escapeHtml(task.condition_text || "").slice(0, 90)}...</span>
              </td>
              <td>${escapeHtml(item.module || task.section_title || "-")}</td>
              <td>${escapeHtml(item.topic || task.topic_title || "-")}</td>
              <td>${formatDate(item.deadline || pool.deadline)}</td>
              <td><span class="status-pill ${statusClass(item.status)}">${statusText(item.status)}</span></td>
              <td>${formatDuration(item.average_time_seconds || 0)}</td>
              <td>${item.attempts_count || 0}</td>
              <td>${escapeHtml(item.result || "-")}</td>
              <td><a class="button small" href="/tasks/${task.id}?pool_task_id=${item.id}">Перейти к заданию</a></td>
            </tr>
          `;
        })
        .join("");

      return `
        <section class="plan-card">
          <div class="plan-card-header">
            <div>
              <h3>${escapeHtml(pool.title)}</h3>
              <p>Период: ${formatDate(pool.period_start)} — ${formatDate(pool.period_end)}. Дедлайн: ${formatDate(pool.deadline)}</p>
            </div>
            <span class="status-pill ${progress === 100 ? "success" : "warning"}">
              ${progress === 100 ? "План недели выполнен" : `${progress}% выполнено`}
            </span>
          </div>
          <div class="progress-line small"><span style="width:${progress}%"></span></div>
          <div class="table-wrap">
            <table class="weekly-table">
              <thead>
                <tr>
                  <th>Задание</th>
                  <th>Модуль</th>
                  <th>Тема</th>
                  <th>Дедлайн</th>
                  <th>Статус</th>
                  <th>Время</th>
                  <th>Попытки</th>
                  <th>Результат</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </section>
      `;
    })
    .join("");
}

async function renderCourseAttempts(courseId) {
  const target = document.getElementById("attempt-history");
  if (!target) return;

  const dashboard = await api(`/users/${activeUserId()}/dashboard`);
  const attempts = (dashboard.recent_attempts || []).filter((attempt) => attempt.course_id === courseId);

  if (!attempts.length) {
    target.innerHTML = `<div class="empty-card">Пока нет попыток по этому курсу. Начните решение задания в модуле.</div>`;
    return;
  }

  target.innerHTML = attempts.map((attempt) => attemptCard(attempt)).join("");
  bindUploadedPagePreviewActions(target);
}

async function renderAnalytics(courseId) {
  const analyticsTarget = document.getElementById("analytics-panel");
  const forecastTarget = document.getElementById("forecast-panel");
  if (!analyticsTarget && !forecastTarget) return;

  const [analytics, forecast] = await Promise.all([
    api(`/users/${activeUserId()}/analytics?course_id=${courseId}`),
    api(`/users/${activeUserId()}/forecast?course_id=${courseId}`),
  ]);

  if (analyticsTarget) {
    analyticsTarget.innerHTML = `
      ${metricItem("Выполнение плана", `${Math.round(analytics.completion_percent || 0)}%`)}
      ${metricItem("Верные ответы", `${Math.round(analytics.correct_percent || 0)}%`)}
      ${metricItem("Среднее время", formatDuration(analytics.average_time_seconds || 0))}
      ${metricItem("С первой попытки", `${Math.round(analytics.first_try_success_percent || 0)}%`)}
      ${metricItem("Освоено типов", analytics.mastered_task_types_count || 0)}
    `;
  }

  if (forecastTarget) {
    forecastTarget.innerHTML = `
      <article class="forecast-card">
        <h3>Прогноз результата</h3>
        <div class="metric-grid">
          ${metricItem("Первичный балл", forecast.expected_primary_score)}
          ${metricItem("Тестовый балл", forecast.expected_test_score)}
          ${metricItem("Оценка", forecast.predicted_grade)}
          ${metricItem("Уверенность", `${forecast.confidence_percent}%`)}
        </div>
        <p><strong>Риск:</strong> ${escapeHtml(forecast.risk_level)}</p>
        <p><strong>Слабые темы:</strong> ${(forecast.weak_topics || []).map(escapeHtml).join(", ") || "не выявлены"}</p>
        <p><strong>Что подтянуть за неделю:</strong> ${(forecast.weekly_focus || []).map(escapeHtml).join(", ") || "закрепить текущий план"}</p>
      </article>
    `;
  }
}

async function renderTutorMaterials(course) {
  const materials = document.getElementById("materials-list");
  if (materials) {
    materials.innerHTML = (course.sections || [])
      .map(
        (section) => `
          <article class="materials-card">
            <h3>${escapeHtml(section.title)}</h3>
            <p>${escapeHtml(section.description || "")}</p>
            <a class="button small ghost" href="/courses/${course.id}/sections/${section.id}">Открыть материалы модуля</a>
          </article>
        `
      )
      .join("");
  }

  if (!state.chatBound) {
    const form = document.getElementById("chat-form");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await sendTutorMessage(course.id);
    });
    document.querySelectorAll("[data-prompt]").forEach((button) => {
      button.addEventListener("click", () => {
        const input = document.getElementById("chat-input");
        if (input) {
          input.value = button.dataset.prompt || "";
          input.focus();
        }
      });
    });
    state.chatBound = true;
  }
}

async function renderParentReport() {
  const target = document.getElementById("parent-report-panel");
  if (!target) return;

  const report = await api(`/users/${activeUserId()}/parent-report`);
  target.innerHTML = `
    <article class="report-card">
      <h3>${escapeHtml(report.student_name)}</h3>
      <p>${escapeHtml(report.current_level)}</p>
      <div class="metric-grid compact">
        ${metricItem("Выполнено", report.completed_tasks)}
        ${metricItem("Попыток", report.attempts_count)}
        ${metricItem("Верных", `${Math.round(report.correct_percent || 0)}%`)}
        ${metricItem("Прогноз", report.predicted_primary_score)}
      </div>
      <p><strong>Что ученик делал:</strong> ${(report.real_activity || []).map(escapeHtml).join(", ") || "активность пока не зафиксирована"}</p>
      <p><strong>Риски:</strong> ${(report.main_risks || []).map(escapeHtml).join(", ") || "нет критичных рисков"}</p>
      <p><strong>Проседающие темы:</strong> ${(report.weak_topics || []).map(escapeHtml).join(", ") || "не выявлены"}</p>
      <p><strong>Рекомендации:</strong> ${(report.next_week_recommendations || []).map(escapeHtml).join(", ")}</p>
    </article>
  `;
}

async function renderTeacherDashboard() {
  const tableBody = document.getElementById("teacher-attempts-body");
  if (!tableBody) return;

  const data = await api("/teacher/dashboard");
  renderTeacherSummary(data.summary || {});
  renderTeacherStudentList(data.students || []);
  await populateTeacherFilters();
  bindTeacherFilters();
  await loadTeacherAttempts();
}

async function initTeacherAttemptsPage() {
  renderNavigationState();
  await renderTeacherDashboard();
}

async function initTeacherAttemptDetailPage() {
  renderNavigationState();
  const attemptId = Number(document.body.dataset.attemptId);
  if (!attemptId) {
    showModal("Работа не найдена", "Не удалось определить номер попытки.");
    return;
  }
  await openTeacherAttempt(attemptId);
}

function renderTeacherStudentList(students) {
  const target = document.getElementById("teacher-student-list");
  if (!target) return;
  target.innerHTML = students
    .map(
      (student) => `
        <article class="teacher-student-card">
          <strong>${escapeHtml(student.name)}</strong>
          <span>${escapeHtml(student.grade || "")} • ${escapeHtml(student.target_exam || "")}</span>
          <span>${Math.round(student.progress || 0)}% плана • ${Math.round(student.correct_percent || 0)}% верных • риск: ${escapeHtml(student.risk_level || "средний")}</span>
        </article>
      `
    )
    .join("");
}

function renderTeacherSummary(summary) {
  const target = document.getElementById("teacher-summary");
  if (!target) return;

  target.innerHTML = `
    ${metricItem("Учеников всего", summary.students_total || 0)}
    ${metricItem("Работ на проверке", summary.works_for_review || 0)}
    ${metricItem("Проверено ИИ", summary.checked_by_ai || 0)}
    ${metricItem("Требует ручной проверки", summary.manual_required || 0)}
    ${metricItem("Средний процент верных", `${Math.round(summary.average_correct_percent || 0)}%`)}
  `;
}

async function populateTeacherFilters() {
  const userSelect = document.getElementById("teacher-filter-user");
  const courseSelect = document.getElementById("teacher-filter-course");
  const sectionSelect = document.getElementById("teacher-filter-section");
  const topicSelect = document.getElementById("teacher-filter-topic");
  if (!userSelect || !courseSelect || !sectionSelect || !topicSelect) return;

  const selectedUser = userSelect.value;
  const selectedCourse = courseSelect.value;
  const selectedSection = sectionSelect.value;
  const selectedTopic = topicSelect.value;

  if (!state.courses.length) {
    state.courses = await api(`/courses?user_id=${activeUserId()}`);
  }

  userSelect.innerHTML = `<option value="">Все ученики</option>${state.users
    .filter((user) => isStudent(user))
    .map((user) => `<option value="${user.id}">${escapeHtml(user.name)}</option>`)
    .join("")}`;
  userSelect.value = selectedUser;

  courseSelect.innerHTML = `<option value="">Все курсы</option>${state.courses
    .map((course) => `<option value="${course.id}">${escapeHtml(course.exam_type)} — ${escapeHtml(course.title)}</option>`)
    .join("")}`;
  courseSelect.value = selectedCourse || "";

  const courseForFilters = courseSelect.value ? await api(`/courses/${courseSelect.value}?user_id=${activeUserId()}`) : state.currentCourse;
  const sections = courseForFilters?.sections || [];
  sectionSelect.innerHTML = `<option value="">Все модули</option>${sections
    .map((section) => `<option value="${section.id}">${escapeHtml(section.title)}</option>`)
    .join("")}`;
  sectionSelect.value = selectedSection;

  const topics = [];
  for (const section of sections) {
    const sectionDetail = await api(`/courses/${courseForFilters.id}/sections/${section.id}?user_id=${activeUserId()}`);
    topics.push(...(sectionDetail.topics || []));
  }
  topicSelect.innerHTML = `<option value="">Все темы</option>${topics
    .map((topic) => `<option value="${topic.id}">${escapeHtml(topic.title)}</option>`)
    .join("")}`;
  topicSelect.value = selectedTopic;
}

function bindTeacherFilters() {
  if (state.teacherPanelBound) return;
  state.teacherPanelBound = true;

  document.getElementById("teacher-filters")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadTeacherAttempts();
  });

  document.getElementById("teacher-filter-course")?.addEventListener("change", async () => {
    document.getElementById("teacher-filter-section").value = "";
    document.getElementById("teacher-filter-topic").value = "";
    await populateTeacherFilters();
    await loadTeacherAttempts();
  });

  document.getElementById("teacher-status-tabs")?.querySelectorAll("[data-teacher-status-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.teacherStatusTab = button.dataset.teacherStatusTab || "";
      document.querySelectorAll("[data-teacher-status-tab]").forEach((tab) => {
        tab.classList.toggle("active", tab === button);
      });
      const statusSelect = document.getElementById("teacher-filter-status");
      if (statusSelect) statusSelect.value = "";
      await loadTeacherAttempts();
    });
  });

  ["teacher-filter-search", "teacher-sort", "teacher-filter-status"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => loadTeacherAttempts());
  });
  document.getElementById("teacher-filter-search")?.addEventListener("input", debounce(() => loadTeacherAttempts(false), 250));
}

async function loadTeacherAttempts(openFirst = true) {
  const tableBody = document.getElementById("teacher-attempts-body");
  if (!tableBody) return;

  const params = new URLSearchParams();
  const fieldMap = [
    ["teacher-filter-user", "user_id"],
    ["teacher-filter-course", "course_id"],
    ["teacher-filter-status", "status"],
    ["teacher-filter-section", "section_id"],
    ["teacher-filter-topic", "topic_id"],
    ["teacher-filter-task", "task_title"],
  ];
  fieldMap.forEach(([id, key]) => {
    const value = document.getElementById(id)?.value?.trim();
    if (value) params.set(key, value);
  });
  const dateFrom = document.getElementById("teacher-filter-date-from")?.value;
  const dateTo = document.getElementById("teacher-filter-date-to")?.value;
  if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00`);
  if (dateTo) params.set("date_to", `${dateTo}T23:59:59`);

  let attempts = await api(`/teacher/attempts?${params.toString()}`);
  attempts = applyTeacherClientFilters(attempts);
  state.teacherAttempts = attempts;
  renderTeacherAttemptsTable(attempts);
  if (openFirst && attempts.length && document.getElementById("teacher-attempt-detail")) {
    await openTeacherAttempt(attempts[0].id);
  }
  if (!attempts.length) {
    const detail = document.getElementById("teacher-attempt-detail");
    if (detail) {
      detail.innerHTML = `<h3>Пока нет отправленных работ на проверку</h3><p class="muted-text">Когда ученик отправит решение, оно появится в этой таблице.</p>`;
    }
  }
}

function applyTeacherClientFilters(attempts) {
  const search = document.getElementById("teacher-filter-search")?.value?.trim().toLowerCase() || "";
  const sort = document.getElementById("teacher-sort")?.value || "date_desc";
  const tab = state.teacherStatusTab || "";
  let result = [...attempts];

  if (tab) {
    const reviewStatuses = new Set(["отправлено", "проверяется ИИ", "требует ручной проверки", "нужна ручная проверка", "manual_review", "проверено", "проверено ИИ"]);
    const checkedStatuses = new Set(["проверено", "проверено ИИ", "проверено преподавателем"]);
    result = result.filter((attempt) => {
      const status = attempt.status || "";
      if (tab === "review") return reviewStatuses.has(status);
      if (tab === "checked") return checkedStatuses.has(status);
      return status === tab;
    });
  }

  if (search) {
    result = result.filter((attempt) =>
      [
        attempt.student_name,
        attempt.course_title,
        attempt.course_exam,
        attempt.section_title,
        attempt.topic_title,
        attempt.task_title,
        attempt.task_number,
        attempt.extracted_answer,
      ]
        .join(" ")
        .toLowerCase()
        .includes(search)
    );
  }

  result.sort((left, right) => {
    if (sort === "student") return String(left.student_name || "").localeCompare(String(right.student_name || ""), "ru");
    if (sort === "status") return statusText(left.status).localeCompare(statusText(right.status), "ru");
    const leftDate = new Date(left.committed_at || left.started_at || 0).getTime();
    const rightDate = new Date(right.committed_at || right.started_at || 0).getTime();
    return sort === "date_asc" ? leftDate - rightDate : rightDate - leftDate;
  });

  return result;
}

function renderTeacherAttemptsTable(attempts) {
  const tableBody = document.getElementById("teacher-attempts-body");
  if (!tableBody) return;

  if (!attempts.length) {
    tableBody.innerHTML = `<tr><td colspan="11">Пока нет отправленных работ на проверку.</td></tr>`;
    return;
  }

  tableBody.innerHTML = attempts
    .map(
      (attempt) => {
        const solutionInfo = attempt.file
          ? `Файл: ${escapeHtml(attempt.file.name || "решение")}`
          : escapeHtml(attempt.extracted_answer || attempt.recognized_text || "файл отсутствует");
        return `
        <tr data-teacher-row="${attempt.id}">
          <td><strong>${escapeHtml(attempt.student_name)}</strong><span class="cell-note">${escapeHtml(attempt.student_grade || "")}</span></td>
          <td>${escapeHtml(attempt.course_exam || attempt.course_title || "-")}</td>
          <td>${escapeHtml(attempt.task_number || attempt.task_title || "-")}</td>
          <td>${escapeHtml(attempt.topic_title || "-")}</td>
          <td>${attempt.attempt_number}</td>
          <td>${formatDateTime(attempt.committed_at || attempt.started_at)}</td>
          <td>${formatDuration(attempt.duration_seconds || 0)}</td>
          <td class="teacher-answer-cell">${solutionInfo}</td>
          <td><span class="status-pill ${teacherStatusClass(attempt.status)}">${escapeHtml(statusText(attempt.status || "-"))}</span></td>
          <td>${attempt.score ?? "-"}</td>
          <td><a class="button small primary" href="/teacher/attempts/${attempt.id}?user_id=${activeUserId()}">Открыть работу</a></td>
        </tr>
      `;
      }
    )
    .join("");
}

async function openTeacherAttempt(attemptId) {
  const detail = await api(`/teacher/attempts/${attemptId}`);
  state.currentTeacherAttempt = detail;

  document.querySelectorAll("[data-teacher-row]").forEach((row) => {
    row.classList.toggle("selected", Number(row.dataset.teacherRow) === attemptId);
  });

  renderTeacherAttemptDetail(detail);
}

function renderTeacherAttemptDetail(detail) {
  const target = document.getElementById("teacher-attempt-detail");
  if (!target) return;

  const attempt = detail.attempt || {};
  const task = detail.task || {};
  const student = detail.student || {};
  const course = detail.course || {};
  const section = detail.section || {};
  const topic = detail.topic || {};
  const latestReview = (detail.ai_reviews || [])[detail.ai_reviews.length - 1] || {};
  const latestComment = (detail.teacher_comments || [])[detail.teacher_comments.length - 1] || {};

  target.innerHTML = `
    <div class="review-header-card">
      <div>
        <p class="section-label">Работа на проверке</p>
        <h3>${escapeHtml(student.name || "Ученик")}</h3>
        <p>${escapeHtml(course.title || "-")} • ${escapeHtml(section.title || "-")} • ${escapeHtml(topic.title || "-")}</p>
      </div>
      <div class="review-header-actions">
        <span class="status-pill ${teacherStatusClass(attempt.status)}">${escapeHtml(statusText(attempt.status || "-"))}</span>
        <a class="button button-ghost" href="/teacher/attempts?user_id=${activeUserId()}">К списку работ</a>
      </div>
    </div>

    <div class="review-metric-strip">
      ${metricItem("Задание", task.title || "-")}
      ${metricItem("Попытка", attempt.attempt_number || "-")}
      ${metricItem("Время решения", formatDuration(attempt.duration_seconds || 0))}
      ${metricItem("Балл", `${attempt.score ?? 0} / ${task.max_score ?? "-"}`)}
      ${metricItem("Автопроверка", attempt.is_correct === true ? "верно" : attempt.is_correct === false ? "неверно" : "ручная проверка")}
    </div>

    <div class="teacher-review-layout">
      <div class="teacher-review-main">
        ${renderTeacherFileBlock(detail.file, detail.solution_pages || attempt.solution_pages || [])}

        <section class="teacher-detail-section">
          <h4>Условие и критерии</h4>
          ${renderTeacherTaskImageBlock(task)}
          <p><strong>Условие:</strong> ${escapeHtml(task.condition_text || "-")}</p>
          <p><strong>Правильный ответ:</strong> ${escapeHtml(task.correct_answer || "-")}</p>
          <p><strong>Решение/пояснение:</strong> ${escapeHtml(task.solution || task.solution_explanation || "-")}</p>
          <p><strong>Критерии:</strong> ${escapeHtml(task.criteria || "-")}</p>
        </section>

        <section class="teacher-detail-section">
          <h4>Данные решения</h4>
          <div class="review-answer-grid">
            <div>
              <span>Начало</span>
              <strong>${formatDateTime(attempt.started_at)}</strong>
            </div>
            <div>
              <span>Завершение</span>
              <strong>${formatDateTime(attempt.committed_at)}</strong>
            </div>
            <div>
              <span>Извлечённый ответ</span>
              <strong>${escapeHtml(attempt.extracted_answer || "-")}</strong>
            </div>
            <div>
              <span>Статус</span>
              <strong>${attempt.is_correct === true ? "верно" : attempt.is_correct === false ? "неверно" : "требует ручной проверки"}</strong>
            </div>
          </div>
          <p><strong>Распознанный текст:</strong> ${escapeHtml(attempt.recognized_text || "-")}</p>
        </section>

        <section class="teacher-detail-section">
          <h4>Комментарий ИИ</h4>
          <p>${escapeHtml(latestReview.review_text || "ИИ-комментарий пока не сохранён.")}</p>
          <p><strong>Ошибки:</strong> ${escapeHtml(latestReview.mistakes || "существенных ошибок не найдено")}</p>
          <p><strong>Рекомендации:</strong> ${escapeHtml(latestReview.recommendations || "закрепить тему похожими заданиями")}</p>
        </section>

        ${renderTeacherMaterialBlock(task.material, topic)}
        ${renderTeacherChatHistory(detail.chat_history)}

        <section class="teacher-detail-section">
          <h4>История попыток по заданию</h4>
          <div class="teacher-history-list">
            ${(detail.history || []).map((item) => renderTeacherHistoryItem(item)).join("")}
          </div>
        </section>
      </div>

      <aside class="teacher-review-sidebar">
        ${renderAdminAttemptDeleteBlock(attempt, student)}

        <section class="teacher-detail-section teacher-check-card">
          <h4>Проверка преподавателя</h4>
          <p class="muted-text">${escapeHtml(latestComment.comment_text || "Комментарий ещё не добавлен.")}</p>
          <form id="teacher-comment-form" class="teacher-comment-form">
            <label>
              Комментарий для ученика
              <textarea id="teacher-comment-text" rows="5" placeholder="Что получилось, где ошибка и что исправить."></textarea>
            </label>
            <div class="teacher-form-row">
              <label>
                Итоговый балл
                <input id="teacher-score-input" type="number" min="0" step="0.5" value="${attempt.score ?? 0}">
              </label>
              <label>
                Статус
                <select id="teacher-status-select">
                  ${teacherStatusOptions(attempt.status)}
                </select>
              </label>
            </div>
            <button class="button button-primary full-width" type="submit">Сохранить проверку</button>
            <div class="teacher-quick-actions">
              <button class="button button-secondary" type="button" data-teacher-status-action="зачтено">Зачесть</button>
              <button class="button button-secondary" type="button" data-teacher-status-action="требуется исправление">На исправление</button>
              <button class="button button-ghost" type="button" data-teacher-status-action="не зачтено">Не зачтено</button>
            </div>
          </form>
        </section>

        <section class="teacher-detail-section">
          <h4>Что проверить вручную</h4>
          <ul class="review-checklist">
            <li>Совпадает ли ход решения с критериями.</li>
            <li>Есть ли математические ошибки в рассуждениях.</li>
            <li>Достаточно ли полно оформлено решение.</li>
            <li>Нужно ли назначить исправление или похожую задачу.</li>
          </ul>
        </section>
      </aside>
    </div>
  `;

  bindTeacherDetailActions(attempt.id, task.id);
}

function renderAdminAttemptDeleteBlock(attempt, student = {}) {
  if (roleKey(activeUser()) !== "admin") return "";
  return `
    <section class="teacher-detail-section admin-danger-card">
      <h4>Администрирование ответа</h4>
      <p class="muted-text">Удаление доступно только администратору. Оно убирает ответ ученика, файл решения, этапы проверки, комментарии ИИ и преподавателя.</p>
      <button class="button button-danger full-width" type="button" data-admin-delete-attempt="${attempt.id}" data-student-name="${escapeHtml(student.name || "ученик")}">Удалить ответ ученика</button>
    </section>
  `;
}

function renderTeacherMaterialBlock(material, topic) {
  if (!material) {
    return `
      <section class="teacher-detail-section">
        <h4>Материал по теме</h4>
        <p class="muted-text">Материал по теме пока не добавлен.</p>
      </section>
    `;
  }
  return `
    <section class="teacher-detail-section">
      <h4>Материал по теме</h4>
      <p><strong>${escapeHtml(material.title || topic?.title || "Учебный материал")}</strong></p>
      <p>${escapeHtml(material.content || "")}</p>
      <p><strong>Пример:</strong> ${escapeHtml(material.examples || "-")}</p>
    </section>
  `;
}

function renderTeacherTaskImageBlock(task) {
  const images = [];
  if (task.context_image_url) {
    images.push({ url: task.context_image_url, title: "Общее условие" });
  }
  if (task.image_url) {
    images.push({ url: task.image_url, title: "Изображение задания" });
  }
  if (!images.length) return "";
  return `
    <div class="teacher-task-images">
      ${images
        .map((image) => {
          const fileName = image.url.split("/").pop() || "task.png";
          return `
            <button class="teacher-image-button" type="button" data-teacher-image="${escapeHtml(image.url)}" data-file-name="${escapeHtml(fileName)}">
              <span>${escapeHtml(image.title)}</span>
              <img class="teacher-file-preview" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.title)}">
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderTeacherChatHistory(chatHistory) {
  const messages = chatHistory?.messages || [];
  if (!messages.length) {
    return `
      <section class="teacher-detail-section">
        <h4>История общения с ИИ-тьютором</h4>
        <p class="muted-text">По этому заданию история диалога отсутствует.</p>
      </section>
    `;
  }

  return `
    <section class="teacher-detail-section">
      <h4>История общения с ИИ-тьютором</h4>
      ${chatHistory.dialog_summary ? `<p><strong>Краткое содержание диалога:</strong> ${escapeHtml(chatHistory.dialog_summary)}</p>` : ""}
      <div class="teacher-chat-history">
        ${messages
          .map(
            (message) => `
              <article class="teacher-chat-message ${message.role === "user" ? "student" : "assistant"}">
                <strong>${message.role === "user" ? "Ученик" : "ИИ-тьютор"}</strong>
                <span>${formatDateTime(message.created_at)}</span>
                <p>${escapeHtml(message.content || "")}</p>
              </article>
            `
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderTeacherFileBlock(file, pages = []) {
  if (pages.length) {
    return `
      <section class="teacher-detail-section">
        <h4>Страницы решения ученика</h4>
        <p class="muted-text">Загружено страниц/файлов: ${pages.length}. Порядок соответствует отправке ученика.</p>
        ${renderUploadedPages(pages)}
      </section>
    `;
  }

  if (!file) {
    return `
      <section class="teacher-detail-section">
        <h4>Загруженное решение</h4>
        <p class="muted-text">Файл решения отсутствует. Для новых попыток ученик должен загрузить фото или файл решения.</p>
      </section>
    `;
  }

  if (file.is_image) {
    return `
      <section class="teacher-detail-section">
        <h4>Фото решения</h4>
        <button class="teacher-image-button" type="button" data-teacher-image="${escapeHtml(file.url)}" data-download-url="${escapeHtml(file.download_url || file.url)}" data-file-name="${escapeHtml(file.name)}">
          <img class="teacher-file-preview" src="${escapeHtml(file.url)}" alt="Фото решения ученика">
        </button>
        <div class="card-actions">
          <a class="button button-secondary" href="${escapeHtml(file.url)}" target="_blank" rel="noreferrer">Открыть в новой вкладке</a>
          <a class="button button-ghost" href="${escapeHtml(file.download_url || file.url)}" download="${escapeHtml(file.name)}">Скачать файл</a>
        </div>
        <p class="muted-text">${escapeHtml(file.name)} • ${formatDateTime(file.uploaded_at)}</p>
      </section>
    `;
  }

  if (file.is_pdf) {
    return `
      <section class="teacher-detail-section">
        <h4>PDF-решение</h4>
        <p>${escapeHtml(file.name)} • ${formatDateTime(file.uploaded_at)}</p>
        <div class="card-actions">
          <a class="button button-secondary" href="${escapeHtml(file.url)}" target="_blank" rel="noreferrer">Открыть PDF</a>
          <a class="button button-ghost" href="${escapeHtml(file.download_url || file.url)}" download="${escapeHtml(file.name)}">Скачать файл</a>
        </div>
      </section>
    `;
  }

  return `
    <section class="teacher-detail-section">
      <h4>Файл решения</h4>
      <p>${escapeHtml(file.name)} • ${formatDateTime(file.uploaded_at)}</p>
      <a class="button button-ghost" href="${escapeHtml(file.download_url || file.url)}" download="${escapeHtml(file.name)}">Скачать файл</a>
    </section>
  `;
}

function renderTeacherHistoryItem(item) {
  const pages = item.solution_pages || [];
  const fileLink = pages.length
    ? pages.map((page) => `<a class="button small ghost" href="${escapeHtml(page.url)}" target="_blank" rel="noreferrer">Страница ${page.page_order || 1}</a>`).join("")
    : item.file
    ? `<a class="button small ghost" href="${escapeHtml(item.file.url)}" target="_blank" rel="noreferrer">Открыть файл</a>`
    : `<span class="muted-text">файл отсутствует</span>`;
  const deleteAction =
    roleKey(activeUser()) === "admin"
      ? `<button class="button small button-danger" type="button" data-admin-delete-attempt="${item.id}">Удалить ответ</button>`
      : "";
  return `
    <article class="teacher-history-item">
      <div class="attempt-card-header">
        <strong>Попытка №${item.attempt_number}</strong>
        <span class="status-pill ${item.is_correct ? "success" : "warning"}">${item.is_correct ? "верно" : "ошибка"}</span>
      </div>
      <p>${formatDateTime(item.committed_at || item.started_at)} • ${formatDuration(item.duration_seconds || 0)} • балл: ${item.score ?? 0}</p>
      <p><strong>Извлечённый ответ:</strong> ${escapeHtml(item.extracted_answer || "-")}</p>
      <p><strong>ИИ:</strong> ${escapeHtml(item.short_ai_comment || "комментарий не сохранён")}</p>
      <div class="card-actions compact-actions">${fileLink}${deleteAction}</div>
    </article>
  `;
}

function bindTeacherDetailActions(attemptId, taskId) {
  document.querySelectorAll("[data-teacher-image]").forEach((button) => {
    button.addEventListener("click", () => showImageModal(button.dataset.teacherImage, button.dataset.fileName, button.dataset.downloadUrl));
  });

  document.getElementById("teacher-comment-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveTeacherComment(attemptId);
  });

  document.querySelectorAll("[data-teacher-status-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const status = button.dataset.teacherStatusAction;
      const select = document.getElementById("teacher-status-select");
      if (select) select.value = status;
      await updateTeacherAttemptStatus(attemptId, status);
    });
  });

  document.querySelectorAll("[data-admin-delete-attempt]").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteStudentAttempt(Number(button.dataset.adminDeleteAttempt), attemptId);
    });
  });
}

async function saveTaskReferenceFromForm(formElement, taskId) {
  if (roleKey(activeUser()) !== "admin") {
    showModal("Недостаточно прав", "Эталонное решение и правильный ответ может менять только администратор.");
    return;
  }
  const fileInput = formElement.querySelector('input[name="reference_files"]');
  const payload = new FormData();
  payload.append("admin_id", String(activeUserId()));
  payload.append("correct_answer", (formElement.querySelector('input[name="correct_answer"]')?.value || "").trim());
  payload.append("criteria", (formElement.querySelector('textarea[name="criteria"]')?.value || "").trim());
  Array.from(fileInput?.files || []).forEach((file) => {
    payload.append("reference_files", file);
  });
  const legacyFile = formElement.querySelector('input[name="reference_file"]')?.files?.[0];
  if (!fileInput?.files?.length && legacyFile) {
    payload.append("reference_file", legacyFile);
  }
  const result = await api(`/admin/tasks/${taskId}/reference-solution`, {
    method: "POST",
    body: payload,
  });
  showModal(
    "Эталон сохранён",
    "Эталонное решение, правильный ответ и критерии сохранены. Следующие проверки будут использовать обновлённые данные."
  );
  return result;
}

async function rerunAttemptAiCheck(attemptId) {
  const result = await api(`/attempts/${attemptId}/check`, { method: "POST" });
  showModal("ИИ-проверка обновлена", "Попытка заново проверена с учётом текущего эталонного решения.");
  await openTeacherAttempt(attemptId);
  await loadTeacherAttempts(false);
  return result;
}

async function deleteStudentAttempt(attemptId, currentAttemptId = null) {
  if (roleKey(activeUser()) !== "admin") {
    showModal("Недостаточно прав", "Удалять ответы учеников может только администратор.");
    return;
  }
  const confirmed = window.confirm("Удалить ответ ученика? Будут удалены файл решения, комментарии и результаты проверки этой попытки.");
  if (!confirmed) return;
  await api(`/admin/attempts/${attemptId}?admin_id=${activeUserId()}`, { method: "DELETE" });
  showModal("Ответ удалён", "Попытка ученика удалена администратором.");

  const page = document.body.dataset.page || "";
  if (page === "teacher-attempt-detail" && Number(document.body.dataset.attemptId) === attemptId) {
    location.href = `/teacher/attempts?user_id=${activeUserId()}`;
    return;
  }
  if (currentAttemptId && Number(currentAttemptId) !== Number(attemptId)) {
    await openTeacherAttempt(Number(currentAttemptId));
  } else {
    const detail = document.getElementById("teacher-attempt-detail");
    if (detail) {
      detail.innerHTML = `<h3>Ответ удалён</h3><p class="muted-text">Выберите другую работу в таблице.</p>`;
    }
  }
  await loadTeacherAttempts(false);
}

async function saveTeacherComment(attemptId) {
  const teacher = teacherUser();
  const scoreValue = document.getElementById("teacher-score-input")?.value;
  const payload = {
    teacher_id: teacher?.id || activeUserId(),
    comment_text: document.getElementById("teacher-comment-text")?.value || "Комментарий преподавателя сохранён.",
    final_score: scoreValue === "" ? null : Number(scoreValue),
    status: document.getElementById("teacher-status-select")?.value || "проверено преподавателем",
  };
  await api(`/teacher/attempts/${attemptId}/comment`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showModal("Комментарий сохранён", "Комментарий преподавателя, итоговый балл и статус проверки сохранены в базе.");
  await openTeacherAttempt(attemptId);
  await loadTeacherAttempts(false);
}

async function updateTeacherAttemptStatus(attemptId, status) {
  const scoreValue = document.getElementById("teacher-score-input")?.value;
  await api(`/teacher/attempts/${attemptId}/status`, {
    method: "POST",
    body: JSON.stringify({
      status,
      score: scoreValue === "" ? null : Number(scoreValue),
    }),
  });
  await openTeacherAttempt(attemptId);
  await loadTeacherAttempts(false);
}

function teacherUser() {
  const current = activeUser();
  if (["teacher", "admin"].includes(roleKey(current))) return current;
  return state.users.find((user) => ["teacher", "admin"].includes(roleKey(user)));
}

function teacherStatusOptions(currentStatus) {
  const statuses = [
    "не начато",
    "в работе",
    "отправлено",
    "проверяется ИИ",
    "проверено ИИ",
    "проверено преподавателем",
    "нужна ручная проверка",
    "manual_review",
    "требуется исправление",
    "зачтено",
    "не зачтено",
  ];
  return statuses
    .map((status) => `<option value="${status}" ${status === currentStatus ? "selected" : ""}>${statusText(status)}</option>`)
    .join("");
}

function teacherStatusClass(status) {
  if (["зачтено", "проверено преподавателем", "проверено ИИ"].includes(status)) return "success";
  if (["отправлено", "проверяется ИИ", "требует ручной проверки", "нужна ручная проверка", "manual_review", "требуется исправление"].includes(status)) return "warning";
  if (status === "не зачтено") return "error";
  return "neutral";
}

function showImageModal(url, fileName, downloadUrl = null) {
  const modal = document.getElementById("image-modal");
  const image = document.getElementById("image-modal-img");
  const openLink = document.getElementById("image-modal-open");
  const downloadLink = document.getElementById("image-modal-download");
  if (!modal || !image || !openLink || !downloadLink) return;
  image.src = url;
  openLink.href = url;
  downloadLink.href = downloadUrl || url;
  downloadLink.download = fileName || "solution.png";
  modal.hidden = false;
  modal.classList.add("visible");
}

function closeImageModal() {
  const modal = document.getElementById("image-modal");
  if (!modal) return;
  modal.classList.remove("visible");
  modal.hidden = true;
}

async function initSectionPage() {
  const courseId = Number(document.body.dataset.courseId);
  const sectionId = Number(document.body.dataset.sectionId);
  const section = await api(`/courses/${courseId}/sections/${sectionId}?user_id=${activeUserId()}`);
  state.currentSection = section;

  renderSectionPage(section);
}

function renderSectionPage(section) {
  const course = section.course || {};
  renderBreadcrumbs([
    { title: "Главная", href: "/" },
    { title: course.title || "Курс", href: `/courses/${course.id}` },
    { title: section.title },
  ]);

  setText("section-title", section.title);
  setText("section-description", section.description || "Модуль подготовки к экзамену.");
  setText("section-theory", section.theory || section.description || "Теория модуля появится в учебных материалах.");

  const stats = document.getElementById("section-stats");
  if (stats) {
    stats.innerHTML = `
      ${metricItem("Тем", section.topic_count || 0)}
      ${metricItem("Заданий", section.task_count || 0)}
      ${metricItem("Прогресс", `${Math.round(section.completion_percent || 0)}%`)}
      ${metricItem("Средний результат", `${Math.round(section.average_result_percent || 0)}%`)}
    `;
  }

  const topicList = document.getElementById("topic-list");
  if (topicList) {
    topicList.innerHTML = (section.topics || []).map((topic) => topicCard(topic, course.id, section.id)).join("");
    bindSectionAdminTaskActions(section);
  }

  const firstTask = section.tasks?.[0] || section.topics?.flatMap((topic) => topic.tasks || [])[0];
  document.getElementById("start-training-button")?.addEventListener("click", () => {
    if (firstTask) {
      location.href = `/tasks/${firstTask.id}`;
    }
  });

  document.getElementById("section-similar-button")?.addEventListener("click", async () => {
    if (!firstTask) return;
    const result = await api(`/tasks/${firstTask.id}/generate-similar`, {
      method: "POST",
      body: JSON.stringify({ count: 3 }),
    });
    showModal("Похожие задания", renderGeneratedTasks(result.tasks || []));
  });

  document.getElementById("ask-section-ai-button")?.addEventListener("click", async () => {
    const answer = await api("/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        user_id: activeUserId(),
        course_id: course.id,
        topic_id: null,
        task_id: null,
        message: `Объясни модуль "${section.title}" и подскажи, с чего начать тренировку.`,
      }),
    });
    showModal("ИИ-тьютор по модулю", answer.answer || answer.content || "ИИ-тьютор подготовил рекомендации по модулю.");
  });
}

function topicCard(topic, courseId, sectionId) {
  const progress = Math.round(topic.mastery_percent || 0);
  const tasks = (topic.tasks || [])
    .map((task) => taskCard(task))
    .join("");

  return `
    <article class="topic-card" id="topic-${topic.id}">
      <div class="topic-header">
        <div>
          <span class="eyebrow">Тема</span>
          <h3>${escapeHtml(topic.title)}</h3>
        </div>
        <span class="status-pill ${progress >= 80 ? "success" : "neutral"}">${progress}% освоения</span>
      </div>
      <p>${escapeHtml(topic.theory_content || "Краткая теория по теме доступна в материалах курса.")}</p>
      <div class="example-box">${escapeHtml(topic.examples || "Пример решения будет показан после открытия темы.")}</div>
      <div class="task-card-grid">${tasks}</div>
      <a class="button secondary" href="/courses/${courseId}/sections/${sectionId}#topic-${topic.id}">Открыть тему</a>
    </article>
  `;
}

function taskCard(task) {
  return `
    <article class="task-card">
      <div class="task-card-header">
        <span>${escapeHtml(task.title)}</span>
        <span class="status-pill ${statusClass(task.status)}">${statusText(task.status)}</span>
      </div>
      <p>${escapeHtml(task.topic_title || task.topic || "Тема")}</p>
      <div class="task-facts">
        <span>${escapeHtml(task.difficulty || "базовый")}</span>
        <span>${task.max_score || 1} балл</span>
        <span>${formatDuration(task.average_time_seconds || 0)}</span>
        <span>${task.attempts_count || 0} попыток</span>
      </div>
      <div class="card-actions compact-actions">
        <a class="button small primary" href="/tasks/${task.id}">Начать решение</a>
        <a class="button small ghost" href="/tasks/${task.id}#history">История попыток</a>
      </div>
      ${renderAdminTaskReferenceControls(task)}
    </article>
  `;
}

function renderAdminTaskReferenceControls(task) {
  if (roleKey(activeUser()) !== "admin") return "";
  const referenceFileUrl = task.reference_solution_file_url || "";
  const referencePages = task.reference_solution_pages || [];
  const hasReferenceFile = Boolean(referencePages.length || task.reference_solution_file_path || task.reference_solution_file_name || referenceFileUrl);
  const pagesBlock = referencePages.length
    ? `<div class="reference-page-list">
        ${referencePages
          .map(
            (page) => `
              <a class="button small ghost" href="${escapeHtml(page.url)}" target="_blank" rel="noreferrer">
                Эталон ${page.page_order || 1}
              </a>
            `
          )
          .join("")}
      </div>`
    : "";
  return `
    <form class="admin-task-reference-form" data-task-reference-form data-task-id="${task.id}" enctype="multipart/form-data" novalidate>
      <div class="admin-form-header">
        <strong>Эталонное решение</strong>
        <span>${hasReferenceFile ? `${referencePages.length || 1} стр.` : "не загружено"}</span>
      </div>
      ${
        referencePages.length
          ? pagesBlock
          : hasReferenceFile && referenceFileUrl
          ? `<a class="button small ghost" href="${escapeHtml(referenceFileUrl)}" target="_blank" rel="noreferrer">Открыть текущий эталон</a>`
          : `<p class="muted-text">Загрузите фото или PDF эталонного решения для проверки ИИ.</p>`
      }
      <label>
        Страницы эталонного решения
        <input name="reference_files" type="file" accept=".jpg,.jpeg,.png,.pdf" multiple>
      </label>
      <p class="muted-text">Можно выбрать несколько фото сразу. При загрузке новых файлов старый эталон будет заменён.</p>
      <label>
        Правильный ответ
        <input name="correct_answer" type="text" value="${escapeHtml(task.correct_answer || "")}" placeholder="Ответ из банка заданий">
      </label>
      <label>
        Критерии оценивания
        <textarea name="criteria" rows="3" placeholder="Критерии проверки решения">${escapeHtml(task.criteria || "")}</textarea>
      </label>
      <button class="button small secondary" type="submit">Сохранить эталон</button>
    </form>
  `;
}

function bindSectionAdminTaskActions(section) {
  if (roleKey(activeUser()) !== "admin") return;
  document.querySelectorAll("[data-task-reference-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const taskId = Number(form.dataset.taskId);
      if (!taskId) return;
      await saveTaskReferenceFromForm(form, taskId);
      const updated = await api(`/courses/${section.course_id}/sections/${section.id}?user_id=${activeUserId()}`);
      state.currentSection = updated;
      renderSectionPage(updated);
    });
  });
}

async function initTaskPage() {
  const taskId = Number(document.body.dataset.taskId);
  const task = await api(`/tasks/${taskId}?user_id=${activeUserId()}`);
  state.currentTask = task;
  renderTaskPage(task);
  await loadTaskAttempts(taskId);
  bindTaskActions(task);
  bindTaskTutor(task);
  await restoreActiveAttempt(taskId);
}

function renderTaskPage(task) {
  const course = task.course || {};
  const section = task.section || {};
  const topic = task.topic || {};

  renderBreadcrumbs([
    { title: "Главная", href: "/" },
    { title: course.title || "Курс", href: `/courses/${course.id}` },
    { title: section.title || "Модуль", href: `/courses/${course.id}/sections/${section.id}` },
    { title: topic.title || "Тема" },
  ]);

  setText("task-title", task.title);
  setText("task-condition", task.condition_text);
  setText("task-criteria", task.criteria || "Критерии оценивания указаны в материалах задания.");
  hideCorrectAnswer();
  setText("task-meta", `${course.exam_type || ""} • ${section.title || ""} • ${topic.title || ""}`);
  const extraMeta = document.getElementById("task-extra-meta");
  if (extraMeta) {
    extraMeta.innerHTML = `
      <span>Тип: ${escapeHtml(task.task_type || "экзаменационное задание")}</span>
      <span>Формат: ${escapeHtml(task.answer_format || "краткий ответ")}</span>
      <span>Сложность: ${escapeHtml(task.difficulty || "базовый")}</span>
      <span>Максимум: ${task.max_score || 1} балл</span>
    `;
  }
  setText("task-topic", topic.title || task.topic_title || "Тема");
  setText("task-difficulty", task.difficulty || "базовый");
  setText("task-max-score", `${task.max_score || 1} балл`);
  renderTaskBankImages(task);
  configureAttemptForm(task);

  const courseLink = document.getElementById("task-course-link");
  if (courseLink) {
    courseLink.href = `/courses/${course.id}`;
    courseLink.textContent = course.title || "Курс";
  }

  const sectionLink = document.getElementById("task-section-link");
  if (sectionLink) {
    sectionLink.href = `/courses/${course.id}/sections/${section.id}`;
    sectionLink.textContent = section.title || "Модуль";
  }

  renderTaskMaterial(task);
  renderPipeline([]);
}

function renderTaskBankImages(task) {
  renderTaskImageBox("task-context-image-box", task.context_image_url, "Общее условие");
  renderTaskImageBox("task-image-box", task.image_url, "Изображение задания");
  const condition = document.getElementById("task-condition");
  if (!condition) return;
  if (task.image_url) {
    condition.textContent = "";
    condition.classList.add("hidden");
  } else {
    condition.textContent = task.condition_text || "";
    condition.classList.remove("hidden");
  }
}

function renderTaskImageBox(elementId, imageUrl, title) {
  const box = document.getElementById(elementId);
  if (!box) return;
  if (!imageUrl) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const fileName = imageUrl.split("/").pop() || "task.png";
  box.classList.remove("hidden");
  box.innerHTML = `
    <div class="task-image-toolbar">
      <strong>${escapeHtml(title)}</strong>
      <button class="button button-ghost small" type="button" data-task-image="${escapeHtml(imageUrl)}" data-file-name="${escapeHtml(fileName)}">Открыть крупнее</button>
    </div>
    <img class="task-bank-image" src="${escapeHtml(imageUrl)}" alt="${escapeHtml(title)}">
  `;
  box.querySelector("[data-task-image]")?.addEventListener("click", (event) => {
    const button = event.currentTarget;
    showImageModal(button.dataset.taskImage, button.dataset.fileName || fileName);
  });
}

function configureAttemptForm(task) {
  const form = document.getElementById("commit-form");
  const shortField = document.getElementById("short-answer-field");
  const commentField = document.getElementById("student-comment-field");
  const fileInput = document.getElementById("solution-file");
  const hint = document.querySelector(".form-hint");
  if (!form) return;
  const isShortAnswer = Number(task.part || 1) === 1;
  form.setAttribute("novalidate", "novalidate");
  form.classList.toggle("short-answer-mode", isShortAnswer);
  form.classList.toggle("extended-answer-mode", !isShortAnswer);
  if (shortField) shortField.hidden = !isShortAnswer;
  if (commentField) commentField.hidden = isShortAnswer;
  if (fileInput) {
    fileInput.required = false;
    fileInput.removeAttribute("required");
    fileInput.multiple = true;
  }
  if (hint) {
    hint.textContent = isShortAnswer
      ? "Для первой части достаточно краткого ответа. Файл можно прикрепить при необходимости."
      : "Для второй части загрузите все страницы решения: JPG, PNG или PDF. Все страницы будут отправлены как одно общее решение одной попытки. Порядок страниц можно изменить перед отправкой.";
  }
  resetSolutionUpload();
}

function bindSolutionUpload() {
  const input = document.getElementById("solution-file");
  const button = document.getElementById("solution-file-button");
  if (!input || input.dataset.bound === "true") return;
  input.dataset.bound = "true";
  button?.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    addSolutionFiles(Array.from(input.files || []));
    input.value = "";
  });
}

function addSolutionFiles(files) {
  if (!files.length) return;
  const total = state.solutionFiles.length + files.length;
  if (total > MAX_SOLUTION_FILES) {
    showModal("Слишком много файлов", `Можно загрузить не более ${MAX_SOLUTION_FILES} страниц решения за одну попытку.`);
    return;
  }

  for (const file of files) {
    if (!SOLUTION_FILE_PATTERN.test(file.name || "")) {
      showModal("Неверный формат файла", "Можно загрузить только JPG, JPEG, PNG или PDF.");
      return;
    }
    if (file.size > MAX_SOLUTION_FILE_SIZE) {
      showModal("Файл слишком большой", `Файл «${escapeHtml(file.name)}» больше 10 МБ. Выберите файл меньшего размера.`);
      return;
    }
  }

  files.forEach((file) => {
    const previewUrl = file.type?.startsWith("image/") ? URL.createObjectURL(file) : "";
    state.solutionFiles.push({ file, previewUrl });
    if (previewUrl) state.solutionFileUrls.push(previewUrl);
  });
  renderSolutionPagesPreview();
}

function resetSolutionUpload() {
  state.solutionFileUrls.forEach((url) => URL.revokeObjectURL(url));
  state.solutionFiles = [];
  state.solutionFileUrls = [];
  renderSolutionPagesPreview();
}

function renderSolutionPagesPreview() {
  const target = document.getElementById("solution-pages-preview");
  if (!target) return;
  if (!state.solutionFiles.length) {
    target.innerHTML = `<p class="muted-text">Страницы решения ещё не выбраны.</p>`;
    return;
  }

  target.innerHTML = state.solutionFiles
    .map(({ file, previewUrl }, index) => {
      const isPdf = /\.pdf$/i.test(file.name || "");
      const thumb = previewUrl
        ? `<img src="${escapeHtml(previewUrl)}" alt="Страница ${index + 1}">`
        : `<span>${isPdf ? "PDF" : "Файл"}</span>`;
      return `
        <article class="solution-page-card" data-solution-index="${index}">
          <div class="solution-page-thumb">${thumb}</div>
          <div class="solution-page-info">
            <strong>Страница ${index + 1}</strong>
            <span title="${escapeHtml(file.name)}">${escapeHtml(file.name)} • ${formatFileSize(file.size)}</span>
            <div class="solution-page-actions">
              <button class="button button-ghost" type="button" data-page-action="up" ${index === 0 ? "disabled" : ""}>Выше</button>
              <button class="button button-ghost" type="button" data-page-action="down" ${index === state.solutionFiles.length - 1 ? "disabled" : ""}>Ниже</button>
              <button class="button button-ghost" type="button" data-page-action="remove">Удалить</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  target.querySelectorAll("[data-page-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest("[data-solution-index]");
      const index = Number(card?.dataset.solutionIndex);
      const action = button.dataset.pageAction;
      updateSolutionFileOrder(index, action);
    });
  });
}

function updateSolutionFileOrder(index, action) {
  if (!Number.isInteger(index) || index < 0 || index >= state.solutionFiles.length) return;
  if (action === "remove") {
    const [removed] = state.solutionFiles.splice(index, 1);
    if (removed?.previewUrl) {
      URL.revokeObjectURL(removed.previewUrl);
      state.solutionFileUrls = state.solutionFileUrls.filter((url) => url !== removed.previewUrl);
    }
  }
  if (action === "up" && index > 0) {
    [state.solutionFiles[index - 1], state.solutionFiles[index]] = [state.solutionFiles[index], state.solutionFiles[index - 1]];
  }
  if (action === "down" && index < state.solutionFiles.length - 1) {
    [state.solutionFiles[index + 1], state.solutionFiles[index]] = [state.solutionFiles[index], state.solutionFiles[index + 1]];
  }
  renderSolutionPagesPreview();
}

function formatFileSize(bytes) {
  if (!bytes) return "0 КБ";
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

function bindTaskActions(task) {
  bindSolutionUpload();
  document.getElementById("start-attempt-button")?.addEventListener("click", () => startTask(task.id));
  document.getElementById("new-attempt-button")?.addEventListener("click", () => startTask(task.id, { forceNew: true }));
  document.getElementById("commit-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await commitAttempt(task.id);
  });

  document.getElementById("similar-button")?.addEventListener("click", async () => {
    const result = await api(`/tasks/${task.id}/generate-similar`, {
      method: "POST",
      body: JSON.stringify({ count: 3 }),
    });
    showModal("Похожие задания", renderGeneratedTasks(result.tasks || []));
  });

  document.getElementById("material-open-button")?.addEventListener("click", () => showTaskMaterial(task));
}

function bindTaskTutor(task) {
  if (state.chatBound) return;
  const form = document.getElementById("chat-form");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendTutorMessage(task.course?.id || task.course_id);
  });
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById("chat-input");
      if (input) {
        input.value = button.dataset.prompt || "";
        input.focus();
      }
    });
  });
  state.chatBound = true;
}

async function startTask(taskId, options = {}) {
  if (state.currentAttemptId && !options.forceNew) {
    showModal("Задание уже в работе", "Текущая попытка уже создана. Отправьте попытку или создайте новую.");
    return;
  }

  const startButton = document.getElementById("start-attempt-button");
  if (startButton) startButton.disabled = true;

  try {
    const attempt = await api(`/tasks/${taskId}/start`, {
      method: "POST",
      body: JSON.stringify({ user_id: activeUserId(), pool_task_id: currentPoolTaskId() }),
    });

    const attemptId = attempt.attempt_id || attempt.id;
    if (!attemptId) {
      throw new Error("Не удалось создать попытку");
    }

    setActiveAttempt({
      ...attempt,
      id: attempt.id || attemptId,
      attempt_id: attemptId,
      task_id: attempt.task_id || taskId,
      server_started_at: attempt.started_at,
      started_at: new Date().toISOString(),
      status: attempt.status || "в работе",
    });
    renderPipeline([{ step_name: "Файл загружен", status: "pending", message: "Решение пока не отправлено" }]);
  } catch (error) {
    if (startButton) startButton.disabled = false;
    showModal("Не удалось создать попытку", escapeHtml(error.message || "Повторите запуск решения."));
  }
}

async function commitAttempt(taskId) {
  if (!state.currentAttemptId) {
    showModal("Сначала начните решение задания", "Сначала начните решение задания, чтобы создать попытку и запустить таймер.");
    return;
  }

  const form = new FormData();
  const selectedFiles = state.solutionFiles.map((item) => item.file);
  const shortAnswer = (document.getElementById("student-short-answer")?.value || "").trim();
  const studentComment = (document.getElementById("student-comment")?.value || "").trim();
  const isShortAnswerTask = Number(state.currentTask?.part || 1) === 1;
  if (!isShortAnswerTask && !selectedFiles.length) {
    showModal("Загрузите решение", "Для второй части загрузите фото или PDF с решением задания.");
    return;
  }

  if (isShortAnswerTask && !shortAnswer && !selectedFiles.length) {
    showModal("Введите ответ", "Введите краткий ответ или прикрепите файл решения.");
    return;
  }

  selectedFiles.forEach((file) => form.append("solution_files", file));
  form.append("student_text_answer", shortAnswer);
  form.append("student_comment", studentComment);

  const commitButton = document.getElementById("commit-attempt-button");
  if (commitButton) commitButton.disabled = true;
  const clientDurationSeconds = currentTimerSeconds();
  form.append("client_duration_seconds", String(clientDurationSeconds));
  stopTimer();
  updateTimerDisplay(clientDurationSeconds);
  setTimerStatus("Статус: отправляется");
  setText("attempt-status-text", `Попытка отправляется. Зафиксированное время: ${formatDuration(clientDurationSeconds)}.`);

  try {
    const result = await api(`/attempts/${state.currentAttemptId}/submit`, {
      method: "POST",
      body: form,
    });
    const attempt = result.attempt || result;

    state.currentAttempt = attempt;
    stopTimer();
    clearActiveAttemptStorage();
    state.currentAttemptId = null;
    state.currentTaskId = null;
    const startButton = document.getElementById("start-attempt-button");
    if (startButton) startButton.disabled = false;
    setTimerStatus("Статус: отправлено");
    if (Number(state.currentTask?.part || attempt.task_part || 1) === 1) {
      showCorrectAnswer(attempt.correct_answer || state.currentTask?.correct_answer || "-");
    } else {
      hideCorrectAnswer();
    }
    setText(
      "attempt-status-text",
      `Попытка отправлена. Итоговое время: ${formatDuration(attempt.duration_seconds || result.duration_seconds || 0)}. Работа доступна преподавателю.`
    );
    resetSolutionUpload();
    if (result.pipeline || result.review) {
      renderPipeline(result.pipeline || []);
      renderReview(result.review || null);
    } else {
      await renderAttemptResult(attempt.id || attempt.attempt_id);
    }
    await loadTaskAttempts(taskId);
  } catch (error) {
    if (commitButton) commitButton.disabled = false;
    if (state.currentAttemptId && state.timerStartedAt) {
      startTimer(state.timerStartedAt);
      setTimerStatus("Статус: в работе");
    }
    showModal("Не удалось отправить попытку", escapeHtml(error.message || "Проверьте ответ или файл и повторите отправку."));
  }
}

async function renderAttemptResult(attemptId) {
  const [pipeline, review] = await Promise.all([
    api(`/attempts/${attemptId}/pipeline`),
    api(`/attempts/${attemptId}/review`),
  ]);
  renderPipeline(pipeline);
  renderReview(review);
}

async function restoreActiveAttempt(taskId) {
  const storedAttemptId = localStorage.getItem(ACTIVE_ATTEMPT_KEYS.attemptId);
  const storedTaskId = Number(localStorage.getItem(ACTIVE_ATTEMPT_KEYS.taskId));
  const storedStartedAt = localStorage.getItem(ACTIVE_ATTEMPT_KEYS.startedAt);
  if (!storedAttemptId || storedTaskId !== taskId || !storedStartedAt) {
    resetTaskControls();
    return;
  }

  try {
    const attempt = await api(`/attempts/${storedAttemptId}`);
    if (attempt.committed_at || attempt.status === "отправлено") {
      clearActiveAttemptStorage();
      resetTaskControls();
      return;
    }
    setActiveAttempt({
      ...attempt,
      id: attempt.id || attempt.attempt_id || Number(storedAttemptId),
      attempt_id: attempt.attempt_id || attempt.id || Number(storedAttemptId),
      server_started_at: attempt.started_at,
      started_at: storedStartedAt,
    });
  } catch {
    clearActiveAttemptStorage();
    resetTaskControls();
  }
}

function setActiveAttempt(attempt) {
  const attemptId = attempt.attempt_id || attempt.id;
  const taskId = attempt.task_id || Number(document.body.dataset.taskId);
  const startedAt = attempt.started_at;
  if (!attemptId || !startedAt) {
    throw new Error("Не удалось создать попытку");
  }

  state.currentAttempt = attempt;
  state.currentAttemptId = Number(attemptId);
  state.currentTaskId = Number(taskId);
  state.timerStartedAt = new Date(startedAt);

  localStorage.setItem(ACTIVE_ATTEMPT_KEYS.attemptId, String(state.currentAttemptId));
  localStorage.setItem(ACTIVE_ATTEMPT_KEYS.taskId, String(state.currentTaskId));
  localStorage.setItem(ACTIVE_ATTEMPT_KEYS.startedAt, state.timerStartedAt.toISOString());

  startTimer(state.timerStartedAt);
  setTaskControlsInProgress(true);
  setTimerStatus("Статус: в работе");
  setText("attempt-status-text", `Текущее задание в работе. Попытка №${attempt.attempt_number || "-"}.`);
}

function setTaskControlsInProgress(isInProgress) {
  const startButton = document.getElementById("start-attempt-button");
  const commitButton = document.getElementById("commit-attempt-button");
  const form = document.getElementById("commit-form");
  if (startButton) startButton.disabled = isInProgress;
  if (commitButton) commitButton.disabled = !isInProgress;
  form?.classList.remove("hidden");
}

function resetTaskControls() {
  stopTimer();
  state.currentAttempt = null;
  state.currentAttemptId = null;
  state.currentTaskId = null;
  state.timerStartedAt = null;
  const timer = document.getElementById("timer-value");
  if (timer) timer.textContent = "00:00:00";
  setTimerStatus("Статус: не начато");
  setTaskControlsInProgress(false);
}

function clearActiveAttemptStorage() {
  localStorage.removeItem(ACTIVE_ATTEMPT_KEYS.attemptId);
  localStorage.removeItem(ACTIVE_ATTEMPT_KEYS.taskId);
  localStorage.removeItem(ACTIVE_ATTEMPT_KEYS.startedAt);
}

function renderPipeline(steps) {
  const target = document.getElementById("pipeline-list");
  if (!target) return;

  const defaultSteps = [
    "Файл загружен",
    "Текст распознан",
    "Ответ извлечён",
    "Ответ нормализован",
    "Ответ сравнен с эталоном",
    "Решение проанализировано ИИ",
    "Ошибки зафиксированы",
    "Рекомендации сформированы",
  ].map((stepName) => ({ step_name: stepName, status: "pending", message: "" }));

  const list = steps?.length ? steps : defaultSteps;
  target.innerHTML = list
    .map(
      (step) => {
        const message = pipelineMessageForAudience(step);
        return `
          <li class="pipeline-step ${pipelineClass(step.status)}">
            <span>${escapeHtml(step.step_name)}</span>
            <strong>${pipelineStatus(step.status)}</strong>
            ${message ? `<small>${escapeHtml(message)}</small>` : ""}
          </li>
        `;
      }
    )
    .join("");
}

function pipelineMessageForAudience(step) {
  const name = String(step.step_name || "").toLowerCase();
  const message = String(step.message || "");
  const isStudentTaskPage = (document.body.dataset.page || "") === "task";

  if (!isStudentTaskPage) {
    return message;
  }

  if (name.includes("текст") && name.includes("распознан")) {
    const warning = studentOcrWarning(message, step.status);
    return warning || "Файл решения сохранён. Распознанный текст передан преподавателю для проверки.";
  }

  if (name.includes("ответ извлеч")) {
    if (Number(state.currentTask?.part || 1) === 2) {
      return "Для второй части краткий ответ не извлекается: проверяется ход решения по загруженным страницам.";
    }
    return message.includes("не найден")
      ? "Автоматически найти итоговый ответ не удалось. Перепишите ответ отдельной строкой в новой попытке или укажите его в поле ответа."
      : "Итоговый ответ найден и передан на проверку.";
  }

  if (Number(state.currentTask?.part || 1) === 2 && (name.includes("нормализован") || name.includes("сравнен"))) {
    return "Для развёрнутого решения правильный ответ ученику не показывается. Преподаватель проверяет ход решения и оформление.";
  }

  return message;
}

function studentOcrWarning(message, status) {
  const text = String(message || "").toLowerCase();
  if (!message) {
    return "Текст решения не удалось уверенно распознать. Преподаватель проверит загруженный файл вручную.";
  }
  if (status === "manual_review" || text.includes("неуверенно") || text.includes("latub") || text.includes("latu")) {
    if (text.includes("итогов") || text.includes("ответ") || text.includes("latub") || text.includes("latu")) {
      return "Решение сохранено. Строка с итоговым ответом распознана неуверенно: перепишите её крупнее и отдельной строкой в новой попытке или укажите ответ в поле комментария.";
    }
    return "Решение сохранено. Один из фрагментов с формулами распознан неуверенно: перепишите спорную строку крупнее и без сокращений.";
  }
  return "";
}

function renderReview(review) {
  const target = document.getElementById("review-box");
  if (!target) return;

  if (Array.isArray(review)) {
    review = review[0];
  }

  if (!review) {
    target.innerHTML = `<div class="empty-card">Комментарий ИИ появится после проверки.</div>`;
    return;
  }
  const reviewText = cleanStudentReviewText(review.review_text || "Решение проверено.");
  const attentionText = reviewAttentionText(review);
  const recommendationText = cleanStudentReviewText(review.recommendations || "Закрепите тему похожими заданиями.");

  target.innerHTML = `
    <article class="review-card">
      <p class="section-label">Результат проверки</p>
      <h3>Комментарий ИИ</h3>
      <p>${escapeHtml(reviewText)}</p>
      <p><strong>Где проблема:</strong> ${escapeHtml(attentionText)}</p>
      <p><strong>Что сделать:</strong> ${escapeHtml(recommendationText)}</p>
    </article>
  `;
}

function cleanStudentReviewText(text) {
  return String(text || "")
    .replace(/Автоматическая текстовая проверка для второй части не выполняется\.?/gi, "")
    .replace(/OCR[^.]*\./gi, "")
    .replace(/\s+/g, " ")
    .trim() || "Решение сохранено. Преподаватель сможет проверить загруженные страницы.";
}

function reviewAttentionText(review) {
  const raw = String(review.mistakes || "").trim();
  const lower = raw.toLowerCase();
  if (!raw || lower.includes("автоматическая текстовая проверка") || lower.includes("не выполняется")) {
    if (Number(state.currentTask?.part || 1) === 2) {
      return "Проверьте, что на фото видны все преобразования, пояснения и итоговый ответ. Если ИИ указал спорное место, перепишите этот фрагмент крупнее в новой попытке.";
    }
    return "Существенных ошибок не найдено.";
  }
  return cleanStudentReviewText(raw);
}

function renderTaskMaterial(task) {
  const topicLink = document.getElementById("material-topic-link");
  const materialButton = document.getElementById("material-open-button");
  const material = task?.material;
  if (topicLink) {
    topicLink.href = task?.topic_id ? `/topics/${task.topic_id}/material` : "#";
    topicLink.hidden = !material;
  }
  if (materialButton) {
    materialButton.disabled = !material;
    materialButton.textContent = material ? "Открыть материал" : "Материал готовится";
  }
}

function showTaskMaterial(task) {
  const material = task?.material;
  const topicTitle = task?.topic?.title || task?.topic_title || "Тема";
  if (!material) {
    showModal("Материал по теме", "Материал по этой теме пока готовится.");
    return;
  }
  showModal(
    material.title || `Материал по теме «${escapeHtml(topicTitle)}»`,
    `
      <article class="material-modal-content">
        <p class="section-label">${escapeHtml(topicTitle)}</p>
        <h4>Краткое объяснение</h4>
        <p>${escapeHtml(material.content || "Краткое объяснение появится в материале темы.")}</p>
        <h4>Пример решения</h4>
        <p>${escapeHtml(material.examples || "Пример решения будет добавлен преподавателем.")}</p>
        <div class="card-actions">
          <button class="button button-primary" type="button" data-close-modal>Вернуться к заданию</button>
        </div>
      </article>
    `
  );
  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });
}

async function loadTaskAttempts(taskId) {
  const target = document.getElementById("attempt-history");
  if (!target) return;

  const attempts = await api(`/tasks/${taskId}/attempts?user_id=${activeUserId()}`);
  if (!attempts.length) {
    target.innerHTML = `<div class="empty-card">История попыток пуста. Каждая новая попытка будет сохранена без удаления.</div>`;
    return;
  }

  target.innerHTML = attempts.map((attempt) => attemptCard(attempt)).join("");
}

function attemptCard(attempt) {
  const fileLink = attempt.file_url
    ? `<a class="button small ghost" href="${escapeHtml(attempt.file_url)}" target="_blank" rel="noreferrer">Открыть файл решения</a>`
    : `<span class="muted-text">файл не загружен</span>`;
  const pagesBlock = renderUploadedPages(attempt.solution_pages || []);

  return `
    <article class="attempt-card">
      <div class="attempt-card-header">
        <strong>Попытка ${attempt.attempt_number}</strong>
        <span class="status-pill ${attempt.is_correct ? "success" : "warning"}">${attempt.is_correct ? "верно" : "требует внимания"}</span>
      </div>
      <p>${escapeHtml(attempt.task_title || "Задание")} • ${formatDateTime(attempt.committed_at || attempt.started_at)}</p>
      <div class="metric-grid compact">
        ${metricItem("Время", formatDuration(attempt.duration_seconds || 0))}
        ${metricItem("Баллы", attempt.score ?? 0)}
        ${metricItem("Статус", statusText(attempt.status))}
      </div>
      <p><strong>Извлечённый ответ:</strong> ${escapeHtml(attempt.extracted_answer || "ожидает распознавания")}</p>
      ${attempt.task_condition ? `<p><strong>Условие:</strong> ${escapeHtml(attempt.task_condition)}</p>` : ""}
      ${Number(attempt.task_part || 1) === 1 && attempt.correct_answer ? `<p><strong>Правильный ответ:</strong> ${escapeHtml(attempt.correct_answer)}</p>` : ""}
      ${pagesBlock}
      <div class="card-actions compact-actions">${fileLink}</div>
    </article>
  `;
}

function renderUploadedPages(pages) {
  if (!pages.length) return "";
  return `
    <div class="uploaded-pages-grid">
      ${pages
        .map((page) => {
          const title = `Страница ${page.page_order || 1}`;
          const name = page.original_filename || "файл решения";
          const preview = page.is_image
            ? `<button class="teacher-image-button" type="button" data-teacher-image="${escapeHtml(page.url)}" data-download-url="${escapeHtml(page.download_url || page.url)}" data-file-name="${escapeHtml(name)}"><img src="${escapeHtml(page.url)}" alt="${escapeHtml(title)}"></button>`
            : `<div class="solution-page-thumb"><span>${page.is_pdf ? "PDF" : "Файл"}</span></div>`;
          return `
            <article class="uploaded-page-card">
              <strong>${escapeHtml(title)}</strong>
              ${preview}
              <span class="muted-text">${escapeHtml(name)}</span>
              <div class="card-actions compact-actions">
                <a class="button small ghost" href="${escapeHtml(page.url)}" target="_blank" rel="noreferrer">Открыть</a>
                <a class="button small ghost" href="${escapeHtml(page.download_url || page.url)}" download="${escapeHtml(name)}">Скачать</a>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function bindUploadedPagePreviewActions(root = document) {
  root.querySelectorAll("[data-teacher-image]").forEach((button) => {
    if (button.dataset.previewBound === "true") return;
    button.dataset.previewBound = "true";
    button.addEventListener("click", () => showImageModal(button.dataset.teacherImage, button.dataset.fileName, button.dataset.downloadUrl));
  });
}

async function createWeeklyPool() {
  const courseId = Number(document.body.dataset.courseId);
  const result = await api(`/users/${activeUserId()}/assignment-pools`, {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, title: "Индивидуальный план на неделю", period_days: 7 }),
  });
  showModal("План создан", `В план добавлено ${result.pool_tasks?.length || 0} заданий.`);
  await renderWeeklyPlan(courseId);
}

async function sendTutorMessage(courseId) {
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");
  const message = input?.value.trim();
  if (!message) return;

  messages.innerHTML += `<div class="chat-message user">${escapeHtml(message)}</div>`;
  input.value = "";

  const answer = await api("/ai/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: activeUserId(),
      course_id: courseId || state.currentTask?.course?.id || state.currentCourse?.id || null,
      topic_id: state.currentTask?.topic?.id || null,
      task_id: state.currentTask?.id || null,
      attempt_id: state.currentAttemptId || null,
      message,
    }),
  });

  messages.innerHTML += `<div class="chat-message assistant">${escapeHtml(answer.answer || answer.content || "ИИ-тьютор подготовил ответ.")}</div>`;
  messages.scrollTop = messages.scrollHeight;
}

function startTimer(startedAt) {
  stopTimer();
  const update = () => {
    updateTimerDisplay(currentTimerSeconds(startedAt));
  };
  update();
  state.timerInterval = setInterval(update, 1000);
}

function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
}

function currentTimerSeconds(startedAt = state.timerStartedAt) {
  if (!startedAt) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
}

function updateTimerDisplay(seconds) {
  const timer = document.getElementById("timer-value") || document.getElementById("timer");
  if (timer) timer.textContent = formatTimerDuration(seconds);
}

function setTimerStatus(text) {
  setText("timer-status-text", text);
}

function renderBreadcrumbs(items) {
  document.querySelectorAll("#breadcrumbs").forEach((container) => {
    container.innerHTML = items
      .map((item, index) => {
        const isLast = index === items.length - 1;
        if (isLast || !item.href) {
          return `<span>${escapeHtml(item.title)}</span>`;
        }
        return `<a href="${item.href}">${escapeHtml(item.title)}</a>`;
      })
      .join('<span class="crumb-separator">→</span>');
  });
}

function metricItem(label, value) {
  return `<div class="metric-item"><strong>${escapeHtml(String(value ?? "-"))}</strong><span>${escapeHtml(label)}</span></div>`;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value ?? "";
}

function hideCorrectAnswer() {
  const card = document.getElementById("correct-answer-card");
  if (card) card.classList.add("hidden");
  setText("hidden-answer-text", "");
}

function showCorrectAnswer(answer) {
  const card = document.getElementById("correct-answer-card");
  if (card) card.classList.remove("hidden");
  setText("hidden-answer-text", `Правильный ответ: ${answer || "-"}`);
}

function showModal(title, content) {
  const modal = document.getElementById("modal");
  if (!modal) return;
  setText("modal-title", title);
  const body = document.getElementById("modal-body") || document.getElementById("modal-text");
  if (body) {
    body.innerHTML = content;
  }
  modal.hidden = false;
  modal.classList.add("visible");
}

function closeModal() {
  const modal = document.getElementById("modal");
  if (!modal) return;
  modal.classList.remove("visible");
  modal.hidden = true;
}

function renderGeneratedTasks(tasks) {
  if (!tasks.length) return "ИИ подготовит похожие задания после выбора темы.";
  return `
    <div class="similar-task-list">
      ${tasks
        .map(
          (task, index) => `
            <article>
              <strong>Вариант ${index + 1}</strong>
              <p>${escapeHtml(task.condition_text || task.condition || "")}</p>
              <small>${escapeHtml(task.topic || "Тема")} • ${escapeHtml(task.difficulty || "уровень указан в задании")}</small>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function debounce(callback, delay = 250) {
  let timerId = null;
  return (...args) => {
    window.clearTimeout(timerId);
    timerId = window.setTimeout(() => callback(...args), delay);
  };
}

function formatPercent(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "0%";
  return `${Math.round(Number(value) * 100)}%`;
}

function formatTimerDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  return [hours, minutes, rest].map((value) => String(value).padStart(2, "0")).join(":");
}

function formatDuration(seconds) {
  const total = Math.round(Number(seconds) || 0);
  if (total <= 0) return "0 сек";
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes <= 0) return `${rest} сек`;
  if (minutes < 60) return `${minutes} мин ${String(rest).padStart(2, "0")} сек`;
  const hours = Math.floor(minutes / 60);
  return `${hours} ч ${String(minutes % 60).padStart(2, "0")} мин ${String(rest).padStart(2, "0")} сек`;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusText(status) {
  const map = {
    not_started: "Не начато",
    in_progress: "В работе",
    submitted: "Отправлено",
    checked: "Проверено",
    corrected: "Исправлено",
    committed: "Отправлено",
    pending: "Ожидание",
    failed: "Ошибка",
    success: "Успешно",
    "не начато": "Не начато",
    "в работе": "В работе",
    "отправлено": "Отправлено",
    "проверяется ИИ": "Проверяется ИИ",
    "проверено": "Проверено",
    "проверено ИИ": "Проверено ИИ",
    "проверено преподавателем": "Проверено преподавателем",
    manual_review: "Нужна ручная проверка",
    "требует ручной проверки": "Нужна ручная проверка",
    "нужна ручная проверка": "Нужна ручная проверка",
    "требуется исправление": "Требует исправления",
    "исправлено": "Исправлено",
    "зачтено": "Зачтено",
    "не зачтено": "Не зачтено",
  };
  return map[status] || status || "Не начато";
}

function statusClass(status) {
  const normalized = statusText(status).toLowerCase();
  if (normalized.includes("проверено") || normalized.includes("исправлено") || normalized.includes("верно")) return "success";
  if (normalized.includes("работе") || normalized.includes("отправлено") || normalized.includes("ожидание") || normalized.includes("требует") || normalized.includes("нужна")) return "warning";
  return "neutral";
}

function pipelineStatus(status) {
  const map = {
    pending: "ожидание",
    running: "выполняется",
    success: "успешно",
    failed: "ошибка",
    teacher_required: "требуется проверка преподавателя",
    manual_review: "требуется проверка преподавателя",
    ожидание: "ожидание",
    выполняется: "выполняется",
    успешно: "успешно",
    ошибка: "ошибка",
  };
  return map[status] || status || "ожидание";
}

function pipelineClass(status) {
  const text = pipelineStatus(status);
  if (text.includes("успешно")) return "success";
  if (text.includes("ошибка")) return "error";
  if (text.includes("выполняется") || text.includes("преподавателя")) return "warning";
  return "neutral";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
