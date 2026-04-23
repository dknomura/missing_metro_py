# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
# ---
# %%
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import random
from celluloid import Camera
import ipywidgets as widgets
from IPython.display import HTML, display, clear_output


# %%
class NaSchTrafficModel:    
    def __init__(self, num_lanes=1, road_length=100, max_velocity=5, 
                 density=0.2, p_slow=0.3, p_lane_change=0.5, 
                 p_slow_stopped=0.5, cell_length=7.5):
        """
        Initialize the traffic model.
        
        Args:
            num_lanes : int
                Number of lanes (default: 1)
            road_length : int
                Number of cells in each lane (default: 100)
            max_velocity : int
                Maximum velocity in cells per timestep (default: 5)
            density : float
                Initial density of cars (0 to 1) (default: 0.2)
            p_slow : float
                Probability of random slowing for moving cars (default: 0.3)
            p_lane_change : float
                Probability of lane change when conditions are met (default: 0.5)
            p_slow_stopped : float
                Probability of random slowing for stopped cars (default: 0.5)
            cell_length : float
                Length of each cell in meters (default: 7.5)
        """
        self.num_lanes = num_lanes
        self.road_length = road_length
        self.max_velocity = max_velocity
        self.density = density
        self.p_slow = p_slow
        self.p_lane_change = p_lane_change
        self.p_slow_stopped = p_slow_stopped
        self.cell_length = cell_length
        
        self.road = np.zeros((num_lanes, road_length, 2), dtype=int)
        
        self._initialize_cars()
        
        self.flow_history = []
        self.density_history = []
        self.average_velocity_history = []
        
    def _initialize_cars(self):
        """Initialize cars randomly on the road based on density."""
        total_cells = self.num_lanes * self.road_length
        num_cars = int(total_cells * self.density)
        
        all_positions = [(lane, pos) for lane in range(self.num_lanes) 
                        for pos in range(self.road_length)]
        car_positions = random.sample(all_positions, min(num_cars, len(all_positions)))
        
        for lane, pos in car_positions:
            self.road[lane, pos, 0] = 1
            self.road[lane, pos, 1] = random.randint(0, self.max_velocity)
    
    def _distance_to_next_car(self, lane, position):
        """
        Calculate distance (in cells) to the next car in the same lane.
        Returns distance (int) or road_length if no car ahead.
        """
        for d in range(1, self.road_length):
            next_pos = (position + d) % self.road_length
            if self.road[lane, next_pos, 0] == 1:
                return d
        return self.road_length
    
    def _space_in_adjacent_lane(self, lane, position):
        """
        Check if there is more space in adjacent lane.
        Returns True if adjacent lane has more empty cells ahead.
        """
        if self.num_lanes == 1:
            return False
            
        if lane > 0:
            left_space = 0
            for d in range(1, self.max_velocity + 1):
                next_pos = (position + d) % self.road_length
                if self.road[lane - 1, next_pos, 0] == 0:
                    left_space += 1
                else:
                    break
            current_space = 0
            for d in range(1, self.max_velocity + 1):
                next_pos = (position + d) % self.road_length
                if self.road[lane, next_pos, 0] == 0:
                    current_space += 1
                else:
                    break
            if left_space > current_space:
                return True
        
        # Check right lane (if exists)
        if lane < self.num_lanes - 1:
            right_space = 0
            for d in range(1, self.max_velocity + 1):
                next_pos = (position + d) % self.road_length
                if self.road[lane + 1, next_pos, 0] == 0:
                    right_space += 1
                else:
                    break
            current_space = 0
            for d in range(1, self.max_velocity + 1):
                next_pos = (position + d) % self.road_length
                if self.road[lane, next_pos, 0] == 0:
                    current_space += 1
                else:
                    break
            if right_space > current_space:
                return True
        
        return False
    
    def _can_change_lane_safely(self, lane, position, target_lane, velocity):
        """
        Check if changing lanes is safe (won't cause rear-end collision).
        """
        if target_lane < 0 or target_lane >= self.num_lanes:
            return False
        
        if self.road[target_lane, position, 0] == 1:
            return False  # Cell occupied
        
        for d in range(1, velocity + 1):
            behind_pos = (position - d) % self.road_length
            if self.road[target_lane, behind_pos, 0] == 1:
                # Car behind might hit us if we change lanes
                behind_velocity = self.road[target_lane, behind_pos, 1]
                if behind_velocity >= d:  # Car behind could reach our position
                    return False
        
        return True
    
    def update(self):
        """
        Update the traffic model for one timestep.
        Returns the number of cars that passed the end of the road.
        """
        new_road = np.zeros_like(self.road)
        cars_passed = 0
        
        decisions = []
        
        for lane in range(self.num_lanes):
            for position in range(self.road_length):
                if self.road[lane, position, 0] == 1:
                    velocity = self.road[lane, position, 1]
                    
                    new_velocity = min(velocity + 1, self.max_velocity)
                    
                    distance = self._distance_to_next_car(lane, position)
                    new_velocity = min(new_velocity, distance - 1)
                    
                    if new_velocity > 0:
                        if random.random() < self.p_slow:
                            new_velocity = max(0, new_velocity - 1)
                    else:  
                        if random.random() < self.p_slow_stopped:
                            new_velocity = 0  
                            
                    lane_change = False
                    target_lane = lane
                    
                    if self.num_lanes > 1:
                        motivation = (new_velocity > distance - 1) and self._space_in_adjacent_lane(lane, position)
                        
                        if motivation:
                            possible_lanes = []
                            if lane > 0 and self._can_change_lane_safely(lane, position, lane - 1, new_velocity):
                                possible_lanes.append(lane - 1)
                            if lane < self.num_lanes - 1 and self._can_change_lane_safely(lane, position, lane + 1, new_velocity):
                                possible_lanes.append(lane + 1)
                            
                            if possible_lanes and random.random() < self.p_lane_change:
                                lane_change = True
                                target_lane = random.choice(possible_lanes)
                    
                    decisions.append({
                        'old_lane': lane,
                        'old_position': position,
                        'new_lane': target_lane if lane_change else lane,
                        'new_position': (position + new_velocity) % self.road_length,
                        'new_velocity': new_velocity,
                        'lane_change': lane_change
                    })
        
        # Second pass: apply movements (all cars move simultaneously)
        for decision in decisions:
            old_lane = decision['old_lane']
            old_position = decision['old_position']
            new_lane = decision['new_lane']
            new_position = decision['new_position']
            new_velocity = decision['new_velocity']
            
            if new_position < old_position:
                cars_passed += 1
            
            # Move car to new position
            new_road[new_lane, new_position, 0] = 1
            new_road[new_lane, new_position, 1] = new_velocity
        
        # Update road state
        self.road = new_road
        
        # Update statistics
        self._update_statistics(cars_passed)
        
        return cars_passed
    
    def _update_statistics(self, cars_passed):
        """Update flow, density, and average velocity statistics."""
        total_cars = np.sum(self.road[:, :, 0])
        current_density = total_cars / (self.num_lanes * self.road_length)
        
        moving_cars = self.road[:, :, 0] * self.road[:, :, 1]
        total_velocity = np.sum(moving_cars)
        if total_cars > 0:
            avg_velocity = total_velocity / total_cars
        else:
            avg_velocity = 0
        
        # Store history
        self.flow_history.append(cars_passed)
        self.density_history.append(current_density)
        self.average_velocity_history.append(avg_velocity)
    
    def get_statistics(self):
        """Get current statistics."""
        return {
            'flow': self.flow_history[-1] if self.flow_history else 0,
            'density': self.density_history[-1] if self.density_history else 0,
            'avg_velocity': self.average_velocity_history[-1] if self.average_velocity_history else 0,
            'total_cars': np.sum(self.road[:, :, 0])
        }

# %%
class TrafficVisualizer:    
    def __init__(self, model, figsize=(12, 8)):
        self.model = model
        self.fig, self.axes = plt.subplots(2, 2, figsize=figsize)
        self.camera = Camera(self.fig)        
    def visualize_frame(self, frame_num):
        """Visualize a single frame of the simulation."""
        for ax in self.axes.flat:
            ax.clear()
        
        # Plot 1: Road visualization
        ax1 = self.axes[0, 0]
        road_display = np.zeros((self.model.num_lanes, self.model.road_length))
        for lane in range(self.model.num_lanes):
            for pos in range(self.model.road_length):
                if self.model.road[lane, pos, 0] == 1:
                    # Color by velocity
                    velocity = self.model.road[lane, pos, 1]
                    road_display[lane, pos] = velocity + 1  # +1 to distinguish from empty
        
        im = ax1.imshow(road_display, cmap='viridis', aspect='auto', 
                       interpolation='nearest', vmin=0, vmax=self.model.max_velocity + 1)
        ax1.set_title(f'Traffic Simulation (Frame {frame_num})')
        ax1.set_xlabel('Position (cells)')
        ax1.set_ylabel('Lane')
        plt.colorbar(im, ax=ax1, label='Velocity + 1')
        
        # Plot 2: Velocity distribution
        ax2 = self.axes[0, 1]
        velocities = []
        for lane in range(self.model.num_lanes):
            for pos in range(self.model.road_length):
                if self.model.road[lane, pos, 0] == 1:
                    velocities.append(self.model.road[lane, pos, 1])
        
        if velocities:
            ax2.hist(velocities, bins=range(self.model.max_velocity + 2), 
                    alpha=0.7, edgecolor='black')
            ax2.set_xlabel('Velocity (cells/timestep)')
            ax2.set_ylabel('Number of cars')
            ax2.set_title('Velocity Distribution')
            ax2.set_xticks(range(self.model.max_velocity + 1))
        
        # Plot 3: Flow vs Density (fundamental diagram)
        ax3 = self.axes[1, 0]
        if len(self.model.flow_history) > 1:
            ax3.scatter(self.model.density_history, self.model.flow_history, 
                       alpha=0.5, s=10)
            ax3.set_xlabel('Density (cars/cell)')
            ax3.set_ylabel('Flow (cars/timestep)')
            ax3.set_title('Fundamental Diagram')
            ax3.grid(True, alpha=0.3)
        
        # Plot 4: Average velocity over time
        ax4 = self.axes[1, 1]
        if len(self.model.average_velocity_history) > 0:
            ax4.plot(self.model.average_velocity_history, 'b-', linewidth=2)
            ax4.set_xlabel('Time (timesteps)')
            ax4.set_ylabel('Average Velocity (cells/timestep)')
            ax4.set_title('Average Velocity Over Time')
            ax4.grid(True, alpha=0.3)
            ax4.set_ylim(0, self.model.max_velocity)
        
        plt.tight_layout()
        if self.camera is not None:
            self.camera.snap()
        else:
            # Save the current figure as an image in memory
            self.fig.canvas.draw()
            self.frames.append(self.fig.canvas.copy_from_bbox(self.fig.bbox))
    
    def create_animation(self, num_frames=100, interval=200):
        """Create and display animation."""
        for i in range(num_frames):
            self.model.update()
            self.visualize_frame(i)
        
        animation = self.camera.animate(interval=interval)
        plt.close()
        return animation

# %%
def create_interactive_simulation():
    """Create an interactive simulation with widgets."""
    num_lanes_slider = widgets.IntSlider(
        value=2, min=1, max=5, step=1, 
        description='Number of lanes:',
        style={'description_width': 'initial'}
    )
    
    road_length_slider = widgets.IntSlider(
        value=50, min=20, max=200, step=10,
        description='Road length (cells):',
        style={'description_width': 'initial'}
    )
    
    max_velocity_slider = widgets.IntSlider(
        value=5, min=1, max=10, step=1,
        description='Max velocity:',
        style={'description_width': 'initial'}
    )
    
    density_slider = widgets.FloatSlider(
        value=0.3, min=0.05, max=0.8, step=0.05,
        description='Initial density:',
        style={'description_width': 'initial'}
    )
    
    p_slow_slider = widgets.FloatSlider(
        value=0.3, min=0.0, max=1.0, step=0.05,
        description='P(slow) moving:',
        style={'description_width': 'initial'}
    )
    
    p_slow_stopped_slider = widgets.FloatSlider(
        value=0.5, min=0.0, max=1.0, step=0.05,
        description='P(slow) stopped:',
        style={'description_width': 'initial'}
    )
    
    p_lane_change_slider = widgets.FloatSlider(
        value=0.5, min=0.0, max=1.0, step=0.05,
        description='P(lane change):',
        style={'description_width': 'initial'}
    )
    
    num_frames_slider = widgets.IntSlider(
        value=100, min=10, max=500, step=10,
        description='Animation frames:',
        style={'description_width': 'initial'}
    )
    
    run_button = widgets.Button(
        description='Run Simulation',
        button_style='success',
        tooltip='Run the simulation with current parameters'
    )
    
    reset_button = widgets.Button(
        description='Reset Simulation',
        button_style='warning',
        tooltip='Reset the simulation to initial state'
    )
    
    output = widgets.Output()
    
    def run_simulation(button):
        """Run the simulation with current parameters."""
        with output:
            clear_output(wait=True)
            
            # Create model with current parameters
            model = NaSchTrafficModel(
                num_lanes=num_lanes_slider.value,
                road_length=road_length_slider.value,
                max_velocity=max_velocity_slider.value,
                density=density_slider.value,
                p_slow=p_slow_slider.value,
                p_lane_change=p_lane_change_slider.value,
                p_slow_stopped=p_slow_stopped_slider.value
            )
            
            visualizer = TrafficVisualizer(model)
            animation = visualizer.create_animation(
                num_frames=num_frames_slider.value,
                interval=200
            )
            
            # Display animation
            display(HTML(animation.to_jshtml()))
            
            # Display statistics
            stats = model.get_statistics()
            print(f"Simulation Statistics:")
            print(f"  Total cars: {stats['total_cars']}")
            print(f"  Current density: {stats['density']:.3f}")
            print(f"  Average velocity: {stats['avg_velocity']:.2f}")
            print(f"  Flow (last timestep): {stats['flow']}")
    
    def reset_simulation(button):
        """Reset the simulation output."""
        with output:
            clear_output(wait=True)
            print("Simulation reset. Adjust parameters and click 'Run Simulation'.")
    
    # Connect button events
    run_button.on_click(run_simulation)
    reset_button.on_click(reset_simulation)
    
    # Create layout
    controls = widgets.VBox([
        widgets.HTML("<h3>Simulation Parameters</h3>"),
        num_lanes_slider,
        road_length_slider,
        max_velocity_slider,
        density_slider,
        p_slow_slider,
        p_slow_stopped_slider,
        p_lane_change_slider,
        num_frames_slider,
        widgets.HBox([run_button, reset_button])
    ])
    
    display(widgets.VBox([controls, output]))
    
    with output:
        print("Adjust parameters above and click 'Run Simulation' to start.")

create_interactive_simulation()
# %%
def run_demo():
    """Run a demo simulation with default parameters."""
    print("NaSch Traffic Model Demo")
    print("========================")
    
    # Create model
    model = NaSchTrafficModel(
        num_lanes=2,
        road_length=50,
        max_velocity=5,
        density=0.3,
        p_slow=0.3,
        p_lane_change=0.5,
        p_slow_stopped=0.5
    )
    
    # Run simulation for a few steps
    print("Running simulation for 10 timesteps...")
    for i in range(10):
        cars_passed = model.update()
        stats = model.get_statistics()
        print(f"Timestep {i+1}: Flow={cars_passed}, Density={stats['density']:.3f}, Avg Velocity={stats['avg_velocity']:.2f}")
    
    print("\nCreating animation...")
    visualizer = TrafficVisualizer(model)
    animation = visualizer.create_animation(num_frames=50, interval=200)
    
    # Display animation
    display(HTML(animation.to_jshtml()))
    
    return model, visualizer

run_demo()
# %%
if __name__ == "__main__":
    # This allows the file to be run as a script
    print("NaSch Traffic Cellular Automata")
    print("================================")
    print("This file is designed to be run in a Jupyter notebook.")
    print("To use interactively:")
    print("1. Run: create_interactive_simulation()")
    print("2. Or run: run_demo()")
    print("\nFor command-line testing, you can run a simple simulation:")
    
    # Simple command-line test
    model = NaSchTrafficModel(num_lanes=1, road_length=20, density=0.3)
    print("\nSimple test simulation (1 lane, 20 cells, 30% density):")
    for i in range(5):
        cars_passed = model.update()
        print(f"Timestep {i+1}: {cars_passed} cars passed")
