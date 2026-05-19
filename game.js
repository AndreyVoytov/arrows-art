(async () => {
  const GAME_WIDTH = 720;
  const GAME_HEIGHT = 960;
  const BATCH_SIZE = 3;
  const BUTTON_SIZE = 82;
  const OUT_DISTANCE = 164;
  const STEP_DELAY = 120;

  const shell = document.querySelector("#game-shell");
  const game = document.querySelector("#game");
  const itemsLayer = document.querySelector("#items");
  const actionsLayer = document.querySelector("#actions");
  const status = document.querySelector("#status");

  syncScale();
  window.addEventListener("resize", syncScale);

  const [roomConfig, orderConfig] = await Promise.all([
    fetch("config/room1.json").then((response) => response.json()),
    fetch("config/room1_order.json").then((response) => response.json())
  ]);

  const orders = {
    repair: normalizeOrder(orderConfig.repair),
    decor: normalizeOrder(orderConfig.decor)
  };
  const phaseByGroup = buildPhaseMap(orders);

  const sprites = roomConfig.objects.map((object, index) => {
    const phase = phaseByGroup.get(object.group);
    const element = document.createElement("img");
    element.className = "sprite";
    element.src = `images/room1/${object.id}.png`;
    element.alt = "";
    element.dataset.id = object.id;
    element.dataset.group = object.group;
    element.dataset.phase = phase;
    element.style.left = `${object.x}px`;
    element.style.top = `${object.y}px`;
    element.style.width = `${object.width}px`;
    element.style.height = `${object.height}px`;
    element.style.zIndex = String(index + 2);

    if (phase === "decor") {
      element.classList.add("hidden");
      element.style.opacity = "0";
    } else {
      element.style.opacity = "1";
    }

    itemsLayer.appendChild(element);
    return { ...object, phase, order: index, element, done: phase === "decor" };
  });

  const state = {
    phase: "repair",
    cursor: 0,
    batch: [],
    busy: false
  };

  showNextBatch();

  function normalizeOrder(entries) {
    return entries.map((entry) => {
      if (typeof entry === "string") {
        const curly = entry.match(/\{(-?\d+)\}$/);
        const square = entry.match(/\[(-?\d+)\]$/);
        const angleMatch = curly ?? square;
        return {
          group: normalizeGroup(entry),
          angle: angleMatch ? Number(angleMatch[1]) : null,
          done: false
        };
      }

      return {
        group: normalizeGroup(entry.group ?? entry.id ?? ""),
        angle: Number.isFinite(entry.angle) ? entry.angle : null,
        done: false
      };
    });
  }

  function normalizeGroup(value) {
    return value
      .replace(/\{(-?\d+)\}$/, "")
      .replace(/\[(-?\d+)\]$/, "")
      .replace(/_\d+$/, "");
  }

  function buildPhaseMap(normalizedOrders) {
    const map = new Map();

    for (const action of normalizedOrders.repair) {
      map.set(action.group, "repair");
    }

    for (const action of normalizedOrders.decor) {
      map.set(action.group, "decor");
    }

    return map;
  }

  function angleFromId(id) {
    const match = id.match(/\[(-?\d+)\]$/);
    return match ? Number(match[1]) : 0;
  }

  function naturalIndex(id) {
    const match = id.replace(/\[(-?\d+)\]$/, "").match(/_(\d+)$/);
    return match ? Number(match[1]) : Number.POSITIVE_INFINITY;
  }

  function objectsFor(action, phase) {
    return sprites
      .filter((sprite) => sprite.phase === phase && sprite.group === action.group)
      .sort((left, right) => {
        const diff = naturalIndex(left.id) - naturalIndex(right.id);
        return diff || left.order - right.order;
      });
  }

  function showNextBatch() {
    actionsLayer.replaceChildren();
    state.busy = false;

    const order = orders[state.phase];
    const next = [];

    while (state.cursor < order.length && next.length < BATCH_SIZE) {
      const action = order[state.cursor++];
      if (objectsFor(action, state.phase).length > 0) {
        next.push(action);
      }
    }

    state.batch = next;

    if (next.length === 0) {
      if (state.phase === "repair") {
        state.phase = "decor";
        state.cursor = 0;
        status.textContent = "Decor";
        showNextBatch();
        return;
      }

      status.textContent = "Done";
      return;
    }

    for (const action of next) {
      actionsLayer.appendChild(createActionButton(action));
    }
  }

  function createActionButton(action) {
    const object = objectsFor(action, state.phase)[0];
    const centerX = clamp(object.x + object.width / 2, BUTTON_SIZE / 2, GAME_WIDTH - BUTTON_SIZE / 2);
    const centerY = clamp(object.y + object.height / 2, BUTTON_SIZE / 2, GAME_HEIGHT - BUTTON_SIZE / 2);
    const button = document.createElement("button");

    button.className = "action-button";
    button.type = "button";
    button.style.left = `${centerX}px`;
    button.style.top = `${centerY}px`;
    button.setAttribute("aria-label", action.group);
    button.addEventListener("click", () => runAction(action, button));

    return button;
  }

  async function runAction(action, button) {
    if (action.done || state.busy) {
      return;
    }

    state.busy = true;
    button.disabled = true;
    button.style.opacity = "0";

    if (state.phase === "repair") {
      await removeObjects(action);
    } else {
      await addObjects(action);
    }

    action.done = true;
    button.remove();

    if (state.batch.every((item) => item.done)) {
      window.setTimeout(showNextBatch, 180);
    } else {
      state.busy = false;
    }
  }

  async function removeObjects(action) {
    const objects = objectsFor(action, "repair").filter((object) => !object.done);

    for (const object of objects) {
      const angle = action.angle ?? angleFromId(object.id);
      await animateOut(object, angle);
      object.done = true;
      await wait(STEP_DELAY);
    }
  }

  async function addObjects(action) {
    const objects = objectsFor(action, "decor").filter((object) => object.done);

    for (const object of objects) {
      const angle = action.angle ?? angleFromId(object.id);
      await animateIn(object, angle);
      object.done = false;
      await wait(STEP_DELAY);
    }
  }

  function vectorForAngle(angle) {
    const radians = angle * Math.PI / 180;
    return {
      x: Math.sin(radians),
      y: -Math.cos(radians)
    };
  }

  async function animateOut(object, angle) {
    const element = object.element;
    const stationary = angle === 180;
    const vector = stationary ? { x: 0, y: 0 } : vectorForAngle(angle);
    const dx = Math.round(vector.x * OUT_DISTANCE);
    const dy = Math.round(vector.y * OUT_DISTANCE);

    element.classList.add("animating", "removing");
    element.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(.96)`;
    element.style.opacity = "0";

    await waitForTransition(element);
    element.classList.add("hidden");
    element.classList.remove("animating", "removing");
  }

  async function animateIn(object, angle) {
    const element = object.element;
    const stationary = angle === 180;
    const vector = stationary ? { x: 0, y: 0 } : vectorForAngle(angle);
    const dx = Math.round(vector.x * OUT_DISTANCE);
    const dy = Math.round(vector.y * OUT_DISTANCE);

    element.classList.remove("hidden");
    element.classList.add("animating", "appearing");
    element.style.transform = `translate3d(${dx}px, ${dy}px, 0) scale(.96)`;
    element.style.opacity = "0";

    await nextFrame();
    element.style.transform = "translate3d(0, 0, 0) scale(1)";
    element.style.opacity = "1";

    await waitForTransition(element);
    element.classList.remove("animating", "appearing");
  }

  function waitForTransition(element) {
    return new Promise((resolve) => {
      const fallback = window.setTimeout(resolve, 700);

      element.addEventListener("transitionend", () => {
        window.clearTimeout(fallback);
        resolve();
      }, { once: true });
    });
  }

  function nextFrame() {
    return new Promise((resolve) => {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(resolve);
      });
    });
  }

  function wait(delay) {
    return new Promise((resolve) => window.setTimeout(resolve, delay));
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function syncScale() {
    const scale = Math.min(window.innerWidth / GAME_WIDTH, window.innerHeight / GAME_HEIGHT, 1);

    shell.style.width = `${GAME_WIDTH * scale}px`;
    shell.style.height = `${GAME_HEIGHT * scale}px`;
    game.style.transform = `scale(${scale})`;
  }
})();
