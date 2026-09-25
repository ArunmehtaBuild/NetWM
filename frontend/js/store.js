/**
 * NetWM State Store
 * Small framework-free reactive container with pub/sub.
 * See frontend/PLAN.md
 */

class Store {
  constructor() {
    this.state = {
      payload: null,
      selectedWindow: 0,
      replay: {
        playing: false,
        t: 0,
        speed: 4, // windows/sec
      },
      filters: {
        stage: null,
        minScore: 0,
      },
      jobStatus: null,
      isMock: true,
      demoName: "thursday",
    };

    this.subscribers = new Set();
  }

  /**
   * Get immutable snapshot of current state
   */
  getState() {
    return this.state;
  }

  /**
   * Update state with a partial slice and notify all subscribers
   */
  set(partialState) {
    const prev = this.state;

    // Synchronize replay.t and selectedWindow
    let nextSelectedWindow = partialState.selectedWindow !== undefined
      ? partialState.selectedWindow
      : (partialState.replay?.t !== undefined ? partialState.replay.t : prev.selectedWindow);

    let nextReplay = partialState.replay
      ? { ...prev.replay, ...partialState.replay }
      : { ...prev.replay };

    if (partialState.selectedWindow !== undefined && partialState.replay?.t === undefined) {
      nextReplay.t = partialState.selectedWindow;
    }

    this.state = {
      ...this.state,
      ...partialState,
      selectedWindow: nextSelectedWindow,
      replay: nextReplay,
      filters: partialState.filters ? { ...prev.filters, ...partialState.filters } : prev.filters,
    };

    this.notify(this.state, prev);
  }

  /**
   * Register a subscriber callback (render function)
   * Returns an unsubscribe function
   */
  subscribe(fn) {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  /**
   * Notify all subscribers
   */
  notify(currentState, prevState) {
    for (const fn of this.subscribers) {
      try {
        fn(currentState, prevState);
      } catch (err) {
        console.error("Store subscriber error:", err);
      }
    }
  }
}

export const store = new Store();
