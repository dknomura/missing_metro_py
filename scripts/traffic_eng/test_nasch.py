#!/usr/bin/env python3
"""Test script for NaSch Traffic Model"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from scripts.traffic_eng.cell_automata import NaSchTrafficModel

def test_basic_simulation():
    """Test basic simulation functionality."""
    print("NaSch Traffic Model Test")
    print("=======================")
    
    # Create model
    model = NaSchTrafficModel(
        num_lanes=1,
        road_length=20,
        max_velocity=3,
        density=0.3,
        p_slow=0.3,
        p_lane_change=0.5,
        p_slow_stopped=0.5
    )
    
    # Get initial statistics
    stats = model.get_statistics()
    print(f"Initial state: {stats}")
    print(f"Total cars: {stats['total_cars']}")
    
    # Run simulation for a few steps
    print("\nRunning simulation for 5 timesteps...")
    for i in range(5):
        cars_passed = model.update()
        stats = model.get_statistics()
        print(f"Timestep {i+1}: Flow={cars_passed}, Density={stats['density']:.3f}, Avg Velocity={stats['avg_velocity']:.2f}")
    
    # Test multi-lane simulation
    print("\n\nMulti-lane simulation test (2 lanes)...")
    model2 = NaSchTrafficModel(
        num_lanes=2,
        road_length=30,
        max_velocity=5,
        density=0.4,
        p_slow=0.3,
        p_lane_change=0.7,
        p_slow_stopped=0.5
    )
    
    stats2 = model2.get_statistics()
    print(f"Initial state (2 lanes): {stats2}")
    
    for i in range(3):
        cars_passed = model2.update()
        stats2 = model2.get_statistics()
        print(f"Timestep {i+1}: Flow={cars_passed}, Density={stats2['density']:.3f}, Avg Velocity={stats2['avg_velocity']:.2f}")
    
    print("\nTest completed successfully!")

if __name__ == "__main__":
    try:
        test_basic_simulation()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()