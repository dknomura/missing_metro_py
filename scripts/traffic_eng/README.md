# NaSch Cellular Automata for Microscopic Traffic Modelling

This implementation provides a Nagel-Schreckenberg (NaSch) cellular automata model for microscopic traffic simulation with support for multiple lanes and lane-changing behavior.

## Features

1. **Core NaSch Model**:
   - Acceleration: Cars try to reach maximum velocity
   - Safety: Cars avoid collisions with cars ahead
   - Randomization: Stochastic slowing behavior
   - Different randomization probabilities for moving vs stopped cars

2. **Multi-lane Support**:
   - Lane-changing rules with motivation and feasibility checks
   - Safety checks to prevent rear-end collisions
   - Randomization of lane change decisions

3. **Visualization**:
   - Real-time animation of traffic flow
   - Velocity distribution histograms
   - Fundamental diagram (flow vs density)
   - Average velocity over time tracking

4. **Interactive Notebook**:
   - Adjustable parameters via sliders
   - Real-time simulation updates
   - Statistics display

## Usage

### In a Jupyter Notebook:

```python
# Import the module
from cell_automata_hw import create_interactive_simulation, run_demo, NaSchTrafficModel, TrafficVisualizer

# Option 1: Run interactive simulation with widgets
create_interactive_simulation()

# Option 2: Run a demo
model, visualizer = run_demo()

# Option 3: Use the model directly
model = NaSchTrafficModel(
    num_lanes=2,
    road_length=50,
    max_velocity=5,
    density=0.3,
    p_slow=0.3,
    p_lane_change=0.5,
    p_slow_stopped=0.5
)

# Update the model
for i in range(10):
    cars_passed = model.update()
    stats = model.get_statistics()
    print(f"Timestep {i+1}: Flow={cars_passed}, Density={stats['density']:.3f}")

# Create visualization
visualizer = TrafficVisualizer(model)
animation = visualizer.create_animation(num_frames=100, interval=200)
```

### Parameters:

- `num_lanes`: Number of lanes (default: 1)
- `road_length`: Number of cells per lane (default: 100)
- `max_velocity`: Maximum velocity in cells per timestep (default: 5)
- `density`: Initial car density (0 to 1) (default: 0.2)
- `p_slow`: Probability of random slowing for moving cars (default: 0.3)
- `p_lane_change`: Probability of lane change when conditions are met (default: 0.5)
- `p_slow_stopped`: Probability of random slowing for stopped cars (default: 0.5)
- `cell_length`: Length of each cell in meters (default: 7.5)

## Model Rules

### Single-lane Rules (per timestep):
1. **Acceleration**: `v = min(v + 1, v_max)`
2. **Safety**: `v = min(v, gap - 1)` where gap is distance to next car
3. **Randomization**: With probability `p_slow`, `v = max(v - 1, 0)`
   - For stopped cars: higher probability `p_slow_stopped`

### Multi-lane Rules:
1. **Motivation**: Car wants to change lanes if:
   - New velocity > distance to next car in same lane
   - More space available in adjacent lane
2. **Feasibility**: Lane change is safe if:
   - Target cell is empty
   - No rear-end collision risk from cars behind in target lane
3. **Randomization**: With probability `p_lane_change`, car changes lanes

## Dependencies

Required:
- numpy
- matplotlib

Optional (for full functionality):
- celluloid (for animations)
- ipywidgets (for interactive widgets)
- jupyter (for notebook environment)

Install optional dependencies:
```bash
pip install celluloid ipywidgets
```

## Example Output

The simulation provides:
1. **Road visualization**: Color-coded by velocity
2. **Velocity distribution**: Histogram of car velocities
3. **Fundamental diagram**: Flow vs density relationship
4. **Average velocity**: Time series of mean velocity

## Testing

Run the test script:
```bash
cd scripts/traffic_eng
python test_nasch.py
```

Or use uv:
```bash
uv run python scripts/traffic_eng/test_nasch.py