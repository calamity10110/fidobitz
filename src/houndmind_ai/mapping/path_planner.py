"""
A* path planning for grid/graph maps (for Pi4).
"""

import heapq


def astar(grid, start, goal, passable=lambda v: v == 0):
    """
    grid: 2D list/array, 0=free, 1=obstacle
    start, goal: (x, y) tuples
    passable: function to check if a cell is traversable
    Returns: list of (x, y) from start to goal, or [] if no path
    """
    if not grid or not grid[0]:
        return []

    w, h = len(grid[0]), len(grid)
    gx, gy = goal
    sx, sy = start

    # Early returns for out of bounds
    if not (0 <= sx < w and 0 <= sy < h and passable(grid[sy][sx])):
        return []
    if not (0 <= gx < w and 0 <= gy < h and passable(grid[gy][gx])):
        return []

    open_set = [(abs(gx - sx) + abs(gy - sy), 0, start)]
    came_from = {}
    g_score = {start: 0}

    # ⚡ Bolt: Localize functions and constants for speed in the hot loop
    heappop = heapq.heappop
    heappush = heapq.heappush
    get_g = g_score.get
    inf = float("inf")

    # ⚡ Bolt: Pre-allocate neighbor offsets to avoid tuple allocations in the hot loop
    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))

    while open_set:
        _, cost, node = heappop(open_set)

        if node == goal:
            path = [node]
            curr = node
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return path

        if cost > get_g(node, inf):
            continue

        x, y = node
        tentative_g = cost + 1

        for dx, dy in offsets:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and passable(grid[ny][nx]):
                neighbor = (nx, ny)
                if tentative_g < get_g(neighbor, inf):
                    came_from[neighbor] = node
                    g_score[neighbor] = tentative_g
                    heappush(
                        open_set,
                        (
                            tentative_g + abs(gx - nx) + abs(gy - ny),
                            tentative_g,
                            neighbor,
                        ),
                    )

    return []


def default_path_planning_hook(mapping_state, sample, settings):
    """
    Example hook: plan from current to goal using A* on a grid map.
    mapping_state: dict with 'samples' and (optionally) 'grid_map'
    settings: config dict, may include 'goal' as (x, y)
    Returns: dict with 'path' and 'success'
    """
    grid = mapping_state.get("grid_map")
    start = mapping_state.get("current_cell")
    goal = settings.get("goal")
    if not (grid and start and goal):
        return {"path": [], "success": False}
    path = astar(grid, start, goal)
    return {"path": path, "success": bool(path)}
