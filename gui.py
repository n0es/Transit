import tkinter as tk
from tkinter import ttk
from tkintermapview import TkinterMapView
from sqlalchemy.orm import Session
from Database import Vehicle, Location, get_db_session
from PIL import Image, ImageDraw, ImageTk

class TransitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transit System Monitor")
        self.root.geometry("1000x600")

        # Database Session
        self.db_session: Session = get_db_session()

        # Main Frames
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=3)

        # Vehicle List
        self.list_frame = ttk.LabelFrame(self.main_frame, text="Vehicles", padding="10")
        self.list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.vehicle_list = ttk.Treeview(self.list_frame, columns=("ID", "Status"), show="headings")
        self.vehicle_list.heading("ID", text="Vehicle ID")
        self.vehicle_list.heading("Status", text="Status")
        self.vehicle_list.column("ID", width=100)
        self.vehicle_list.column("Status", width=100)
        self.vehicle_list.grid(row=0, column=0, sticky="nsew")
        list_scrollbar = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.vehicle_list.yview)
        self.vehicle_list.configure(yscroll=list_scrollbar.set)
        list_scrollbar.grid(row=0, column=1, sticky="ns")

        # Map
        self.map_frame = ttk.LabelFrame(self.main_frame, text="Map", padding="10")
        self.map_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.map_frame.grid_rowconfigure(0, weight=1)
        self.map_frame.grid_columnconfigure(0, weight=1)

        self.map_widget = TkinterMapView(self.map_frame, width=600, height=550, corner_radius=0)
        self.map_widget.set_tile_server("https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", max_zoom=22)
        self.map_widget.set_position(40.7128, -74.0060) # NYC
        self.map_widget.set_zoom(10)
        self.map_widget.grid(row=0, column=0, sticky="nsew")
        self.map_widget.update()

        # Vehicle Markers
        self.dot_image = self.create_dot_icon(size=10, color="red")
        self.vehicle_markers = {}

        self.refresh_interval_ms = 2000
        self.update_data()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def get_latest_locations(self) -> dict[str, tuple[float, float]]:
        latest_locations = {}
        try:
            subquery = self.db_session.query(
                Location.vehicle_id,
                func.max(Location.timestamp).label('max_timestamp')
            ).group_by(Location.vehicle_id).subquery()

            results = self.db_session.query(Location).join(
                subquery,
                (Location.vehicle_id == subquery.c.vehicle_id) &
                (Location.timestamp == subquery.c.max_timestamp)
            ).all()

            for loc in results:
                latest_locations[loc.vehicle_id] = (loc.latitude, loc.longitude)
        except Exception as e:
            print(f"Error fetching latest locations: {e}")
            self.db_session.rollback()
        return latest_locations


    def update_data(self):
        try:
            vehicles = self.db_session.query(Vehicle).all()

            selected_items = self.vehicle_list.selection()
            scroll_pos = self.vehicle_list.yview()

            for item in self.vehicle_list.get_children():
                self.vehicle_list.delete(item)

            for vehicle in vehicles:
                self.vehicle_list.insert("", tk.END, values=(vehicle.vehicle_id, vehicle.status))

            valid_selection = [item for item in selected_items if self.vehicle_list.exists(item)]
            if valid_selection:
                self.vehicle_list.selection_set(valid_selection)
            self.vehicle_list.yview_moveto(scroll_pos[0])


            latest_locations = self.get_latest_locations()

            current_marker_ids = set(self.vehicle_markers.keys())
            vehicles_with_location = set(latest_locations.keys())

            first_marker_pos = None
            for vehicle_id, (lat, lon) in latest_locations.items():
                if lat is None or lon is None: continue

                if first_marker_pos is None:
                    first_marker_pos = (lat, lon)

                if vehicle_id in self.vehicle_markers:
                    marker = self.vehicle_markers[vehicle_id]
                    current_pos = marker.position
                    if current_pos[0] != lat or current_pos[1] != lon:
                        marker.set_position(lat, lon)
                    marker.set_text(vehicle_id)
                else:
                    new_marker = self.map_widget.set_marker(
                        lat, lon,
                        text=vehicle_id,
                        icon=self.dot_image,
                        icon_anchor="center"
                    )
                    self.vehicle_markers[vehicle_id] = new_marker

            ids_to_remove = current_marker_ids - vehicles_with_location
            for vehicle_id in ids_to_remove:
                if vehicle_id in self.vehicle_markers:
                    marker_to_remove = self.vehicle_markers[vehicle_id]
                    marker_to_remove.delete()
                    del self.vehicle_markers[vehicle_id]


        except Exception as e:
            print(f"Error updating data: {e}")

        self.root.after(self.refresh_interval_ms, self.update_data)

    def create_dot_icon(self, size: int, color: str) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.ellipse((0, 0, size - 1, size - 1), fill=color, outline=color)
        return ImageTk.PhotoImage(image)


    def on_close(self):
        print("Closing GUI and database session...")
        
        if self.db_session:
            self.db_session.close()
        self.root.destroy()


if __name__ == "__main__":
    from sqlalchemy import func

    root = tk.Tk()
    app = TransitGUI(root)
    root.mainloop() 