(async () => {
  const GAME_WIDTH = 720;
  const GAME_HEIGHT = 960;
  const BATCH_SIZE = 3;
  const BUTTON_SIZE = 82;
  const OUT_DISTANCE = 164;
  const STEP_DELAY = 120;

  const shell = document.querySelector("#game-shell");
  const game = document.querySelector("#game");
  const roomBg = document.querySelector("#room-bg");
  const itemsLayer = document.querySelector("#items");
  const actionsLayer = document.querySelector("#actions");
  const status = document.querySelector("#status");
  const topMenuButton = document.querySelector("#top-menu-button");
  const roomMenu = document.querySelector("#room-menu");
  const roomList = document.querySelector("#room-list");
  const variantPanel = document.querySelector("#variant-panel");
  const variantOptions = document.querySelector("#variant-options");
  const variantChoose = document.querySelector("#variant-choose");
  const variantClose = document.querySelector("#variant-close");

  let currentRoomId = null;
  let orders = { repair: [], decor: [] };
  let phaseByGroup = new Map();
  let sprites = [];
  let state = createInitialState();
  let activeVariant = null;

  syncScale();
  window.addEventListener("resize", syncScale);
  topMenuButton.addEventListener("click", showMenu);
  variantChoose.addEventListener("click", chooseVariant);
  variantClose.addEventListener("click", closeVariantPicker);

  topMenuButton.classList.add("hidden");
  renderRoomMenu(await loadRooms());

  async function loadRooms() {
    try {
      const response = await fetch("config/rooms.json");
      if (!response.ok) {
        throw new Error("rooms manifest not found");
      }

      const manifest = await response.json();
      if (Array.isArray(manifest.rooms) && manifest.rooms.length > 0) {
        return manifest.rooms;
      }
    } catch (error) {
      return discoverRooms();
    }

    return discoverRooms();
  }

  async function discoverRooms() {
    const rooms = [];
    let misses = 0;

    for (let number = 1; number <= 50 && misses < 3; number += 1) {
      if (await roomExists(number)) {
        rooms.push({ id: `room${number}`, number });
        misses = 0;
      } else if (rooms.length > 0) {
        misses += 1;
      }
    }

    return rooms.length > 0 ? rooms : [{ id: "room1", number: 1 }];
  }

  async function roomExists(number) {
    try {
      const response = await fetch(`config/room${number}.json`, { method: "HEAD" });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  function renderRoomMenu(rooms) {
    roomList.replaceChildren();

    for (const room of rooms) {
      const button = document.createElement("button");
      button.className = "room-button";
      button.type = "button";
      button.textContent = room.title ?? `Комната ${room.number ?? room.id.replace("room", "")}`;
      button.addEventListener("click", () => startRoom(room.id));
      roomList.appendChild(button);
    }
  }

  async function startRoom(roomId) {
    currentRoomId = roomId;
    state = createInitialState();
    activeVariant = null;
    orders = { repair: [], decor: [] };
    phaseByGroup = new Map();
    sprites = [];

    itemsLayer.replaceChildren();
    actionsLayer.replaceChildren();
    hideVariantPanel();

    roomBg.src = `images/${roomId}/room_bg.png`;
    roomMenu.classList.add("hidden");
    topMenuButton.classList.remove("hidden");
    status.textContent = "";

    const [roomConfig, orderConfig] = await Promise.all([
      fetch(`config/${roomId}.json`).then((response) => response.json()),
      fetch(`config/${roomId}_order.json`).then((response) => response.json())
    ]);

    orders = {
      repair: normalizeOrder(orderConfig.repair),
      decor: normalizeOrder(orderConfig.decor)
    };
    phaseByGroup = buildPhaseMap(orders);
    sprites = createSprites(roomConfig);

    showNextBatch();
  }

  function showMenu() {
    currentRoomId = null;
    state = createInitialState();
    activeVariant = null;
    itemsLayer.replaceChildren();
    actionsLayer.replaceChildren();
    hideVariantPanel();
    roomBg.removeAttribute("src");
    roomMenu.classList.remove("hidden");
    topMenuButton.classList.add("hidden");
    status.textContent = "";
  }

  function createInitialState() {
    return {
      phase: "repair",
      cursor: 0,
      batch: [],
      busy: false
    };
  }

  function createSprites(roomConfig) {
    return flattenRoomObjects(roomConfig)
      .map((object, index) => {
        const phase = phaseByGroup.get(object.group);
        if (phase === undefined) {
          return null;
        }

        const element = document.createElement("img");
        element.className = "sprite";
        element.src = `images/${currentRoomId}/${object.imageId ?? object.id}.png`;
        element.alt = "";
        element.dataset.id = object.id;
        element.dataset.imageId = object.imageId ?? object.id;
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
        return {
          ...object,
          phase,
          order: index,
          variant: variantFromId(object.id),
          element,
          done: phase === "decor"
        };
      })
      .filter(Boolean);
  }

  function flattenRoomObjects(roomConfig) {
    if (Array.isArray(roomConfig.groups)) {
      return roomConfig.groups.flatMap((group) => {
        return group.objects.map((object) => ({
          ...object,
          group: group.groupId ?? group.id
        }));
      });
    }

    return (roomConfig.objects ?? []).map((object) => ({
      ...object,
      imageId: object.imageId ?? object.id,
      angle: object.angle ?? angleFromId(object.id)
    }));
  }

  function normalizeOrder(entries = []) {
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
      .replace(/_(?:[A-Z])(?:_\d+)?$/, "")
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
    const match = id.trim().match(/\[(-?\d+)\]$/);
    return match ? Number(match[1]) : 0;
  }

  function angleForObject(object) {
    return Number.isFinite(object.angle) ? object.angle : angleFromId(object.id);
  }

  function idWithoutAngle(id) {
    return id.trim().replace(/\[(-?\d+)\]$/, "");
  }

  function variantFromId(id) {
    const match = idWithoutAngle(id).match(/_([A-Z])(?:_\d+)?$/);
    return match ? match[1] : null;
  }

  function naturalIndex(id) {
    const match = idWithoutAngle(id).match(/_(\d+)$/);
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
      finishAction(action, button);
      return;
    }

    const variants = variantsFor(action);
    if (variants.length > 1) {
      await openVariantPicker(action, button, variants);
      return;
    }

    await addObjects(action);
    finishAction(action, button);
  }

  function finishAction(action, button) {
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
      const angle = action.angle ?? angleForObject(object);
      await animateOut(object, angle);
      object.done = true;
      await wait(STEP_DELAY);
    }
  }

  async function addObjects(action) {
    const objects = objectsFor(action, "decor").filter((object) => object.done);

    for (const object of objects) {
      const angle = action.angle ?? angleForObject(object);
      await animateIn(object, angle);
      object.done = false;
      await wait(STEP_DELAY);
    }
  }

  function variantsFor(action) {
    const variants = new Map();

    for (const object of objectsFor(action, "decor")) {
      if (object.variant === null) {
        continue;
      }

      if (!variants.has(object.variant)) {
        variants.set(object.variant, []);
      }

      variants.get(object.variant).push(object);
    }

    return [...variants.entries()]
      .map(([id, objects]) => ({ id, objects }))
      .sort((left, right) => left.id.localeCompare(right.id));
  }

  async function openVariantPicker(action, button, variants) {
    activeVariant = {
      action,
      button,
      variants,
      selected: null,
      busy: false
    };

    renderVariantOptions();
    variantPanel.classList.remove("hidden");

    const defaultVariant = variants.find((variant) => variant.id === "A") ?? variants[0];
    await selectVariant(defaultVariant.id, true);
  }

  function renderVariantOptions() {
    variantOptions.replaceChildren();

    for (const variant of activeVariant.variants) {
      const option = document.createElement("button");
      const preview = document.createElement("img");

      option.className = "variant-option";
      option.type = "button";
      option.setAttribute("aria-label", `Вариант ${variant.id}`);
      option.dataset.variant = variant.id;
      option.addEventListener("click", () => selectVariant(variant.id, false));

      preview.src = `images/${currentRoomId}/${variant.objects[0].imageId ?? variant.objects[0].id}.png`;
      preview.alt = "";
      option.appendChild(preview);
      variantOptions.appendChild(option);
    }
  }

  async function selectVariant(variantId, materialize) {
    if (activeVariant === null || activeVariant.busy || activeVariant.selected === variantId) {
      return;
    }

    activeVariant.busy = true;
    hideVariantObjects(activeVariant.action);

    activeVariant.selected = variantId;
    updateVariantOptionState();

    const selectedObjects = objectsForVariant(variantId);
    for (const object of selectedObjects) {
      object.element.classList.remove("hidden", "animating", "appearing", "removing");
      object.element.style.transform = "translate3d(0, 0, 0) scale(1)";
      object.element.style.opacity = "1";
    }

    if (materialize) {
      await Promise.all(
        selectedObjects.map((object) => animateIn(object, angleForObject(object)))
      );
    } else {
      playVariantSwitch(selectedObjects);
    }

    activeVariant.busy = false;
  }

  function updateVariantOptionState() {
    for (const option of variantOptions.querySelectorAll(".variant-option")) {
      option.classList.toggle("selected", option.dataset.variant === activeVariant.selected);
    }
  }

  function objectsForVariant(variantId) {
    const variant = activeVariant.variants.find((item) => item.id === variantId);
    return variant ? variant.objects : [];
  }

  function hideVariantObjects(action) {
    for (const object of objectsFor(action, "decor")) {
      if (object.variant === null) {
        continue;
      }

      object.element.classList.add("hidden");
      object.element.classList.remove("animating", "appearing", "removing", "variant-switching");
      object.element.style.transform = "translate3d(0, 0, 0) scale(1)";
      object.element.style.opacity = "0";
    }
  }

  function chooseVariant() {
    if (activeVariant === null || activeVariant.busy) {
      return;
    }

    const { action, button, selected } = activeVariant;

    for (const object of objectsFor(action, "decor")) {
      object.done = object.variant !== selected;
      if (object.variant !== selected) {
        object.element.classList.add("hidden");
        object.element.style.opacity = "0";
      }
    }

    hideVariantPanel();
    finishAction(action, button);
  }

  function closeVariantPicker() {
    if (activeVariant === null || activeVariant.busy) {
      return;
    }

    const { action, button } = activeVariant;
    hideVariantObjects(action);
    hideVariantPanel();

    button.disabled = false;
    button.style.opacity = "1";
    state.busy = false;
  }

  function hideVariantPanel() {
    variantPanel.classList.add("hidden");
    variantOptions.replaceChildren();
    activeVariant = null;
  }

  function playVariantSwitch(objects) {
    for (const object of objects) {
      const element = object.element;
      element.classList.remove("variant-switching");
      void element.offsetWidth;
      element.classList.add("variant-switching");
      element.addEventListener("animationend", () => {
        element.classList.remove("variant-switching");
      }, { once: true });
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
