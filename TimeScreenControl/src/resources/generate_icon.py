"""
TimeScreen Control - Generate Application Icon
Creates a professional .ico file for the application.
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(output_path: str = "src/resources/icon.ico"):
    """
    Create a multi-resolution ICO file for TimeScreen Control.
    
    Generates icon with multiple sizes: 16x16, 32x32, 48x48, 64x64, 128x128, 256x256
    """
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Define sizes to generate
    sizes = [16, 32, 48, 64, 128, 256]
    
    images = []
    
    for size in sizes:
        # Create image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate proportions
        margin = size // 8
        inner_margin = size // 4
        
        # Draw background circle (gradient-like effect using solid color)
        bg_color = (26, 26, 46, 255)  # #1a1a2e - dark blue from app theme
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=bg_color
        )
        
        # Draw lock body
        lock_left = inner_margin
        lock_top = size // 3
        lock_right = size - inner_margin
        lock_bottom = size - margin
        
        # Lock body color (red/pink from theme)
        lock_color = (233, 69, 96, 255)  # #e94560
        
        # Draw rounded rectangle for lock body
        corner_radius = size // 10
        draw.rounded_rectangle(
            [lock_left, lock_top, lock_right, lock_bottom],
            radius=corner_radius,
            fill=lock_color
        )
        
        # Draw lock shackle (the U-shaped part on top)
        shackle_width = size // 6
        shackle_top = margin
        shackle_bottom = lock_top + size // 10
        
        # Shackle color (lighter)
        shackle_color = (255, 107, 107, 255)  # #ff6b6b
        
        # Draw shackle as an arc/line
        shackle_center_x = size // 2
        shackle_left = shackle_center_x - size // 5
        shackle_right = shackle_center_x + size // 5
        
        # Draw shackle lines (left and right sides of U)
        draw.line(
            [(shackle_left, shackle_bottom), 
             (shackle_left, shackle_top + size//12)],
            fill=shackle_color,
            width=max(2, shackle_width // 2)
        )
        draw.line(
            [(shackle_right, shackle_bottom), 
             (shackle_right, shackle_top + size//12)],
            fill=shackle_color,
            width=max(2, shackle_width // 2)
        )
        
        # Draw top arc of shackle
        draw.arc(
            [shackle_left, shackle_top, 
             shackle_right, shackle_bottom + size//12],
            start=180,
            end=0,
            fill=shackle_color,
            width=max(2, shackle_width // 2)
        )
        
        # Draw keyhole (simple circle + rectangle)
        keyhole_y = (lock_top + lock_bottom) // 2
        keyhole_size = size // 8
        
        # Keyhole circle
        draw.ellipse(
            [size//2 - keyhole_size//2, keyhole_y - keyhole_size//2,
             size//2 + keyhole_size//2, keyhole_y + keyhole_size//2],
            fill=(26, 26, 46, 255)  # Dark background color
        )
        
        # Keyhole slot (rectangle below circle)
        draw.rectangle(
            [size//2 - keyhole_size//4, keyhole_y,
             size//2 + keyhole_size//4, keyhole_y + keyhole_size//2],
            fill=(26, 26, 46, 255)
        )
        
        images.append(img)
    
    # Save as ICO with all sizes
    images[0].save(
        output_path,
        format='ICO',
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:]
    )
    
    print(f"✅ Icon created: {output_path}")
    print(f"   Sizes: {[f'{img.width}x{img.height}' for img in images]}")
    return output_path


if __name__ == "__main__":
    create_icon()
    print("\nIcon generation complete!")
