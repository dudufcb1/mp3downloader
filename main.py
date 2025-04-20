import customtkinter as ctk
import yt_dlp
import threading
from tkinter import messagebox, filedialog
import os
import re
import json
from queue import Queue, Empty
from threading import Event, Lock
import time
from tkinter import Tk

CONFIG_FILE = "config.json"

class DownloaderApp:
    def __init__(self):
        self.window = ctk.CTk()
        self.window.title("Descargador de Videos/MP3")
        self.window.geometry("600x500")
        
        # Variables de control
        self.download_queue = Queue()
        self.stop_event = Event()
        self.download_thread = None
        self.is_downloading = False
        self.queue_lock = Lock()
        
        # Cargar o crear configuración
        self.load_config()
        
        # Área de URLs
        self.url_label = ctk.CTkLabel(self.window, text="URLs (una por línea):")
        self.url_label.pack(pady=5)
        
        self.url_text = ctk.CTkTextbox(self.window, height=200)
        self.url_text.pack(padx=10, pady=5, fill="x")
        
        # Botón de pegar
        self.paste_button = ctk.CTkButton(self.window, text="Pegar URL", command=self.paste_url)
        self.paste_button.pack(pady=5)
        
        # Botón para cambiar directorio
        self.change_dir_button = ctk.CTkButton(self.window, text="Cambiar Directorio", command=self.change_download_dir)
        self.change_dir_button.pack(pady=5)
        
        # Label para mostrar el directorio actual
        self.dir_label = ctk.CTkLabel(self.window, text=f"Directorio: {self.config['download_path']}")
        self.dir_label.pack(pady=5)
        
        # Selector de formato
        self.format_var = ctk.StringVar(value="mp3")  # Cambiado a mp3
        self.format_label = ctk.CTkLabel(self.window, text="Formato de descarga:")
        self.format_label.pack(pady=5)
        
        self.format_frame = ctk.CTkFrame(self.window)
        self.format_frame.pack(pady=5)
        
        self.mp3_radio = ctk.CTkRadioButton(self.format_frame, text="MP3", variable=self.format_var, value="mp3")
        self.mp3_radio.pack(side="left", padx=10)
        
        self.mp4_radio = ctk.CTkRadioButton(self.format_frame, text="MP4", variable=self.format_var, value="mp4")
        self.mp4_radio.pack(side="left", padx=10)
        
        # Selector de calidad
        self.quality_var = ctk.StringVar(value="high")  # Ya está en alta por defecto
        self.quality_label = ctk.CTkLabel(self.window, text="Calidad:")
        self.quality_label.pack(pady=5)
        
        self.quality_frame = ctk.CTkFrame(self.window)
        self.quality_frame.pack(pady=5)
        
        self.high_radio = ctk.CTkRadioButton(self.quality_frame, text="Alta", variable=self.quality_var, value="high")
        self.high_radio.pack(side="left", padx=10)
        
        self.medium_radio = ctk.CTkRadioButton(self.quality_frame, text="Media", variable=self.quality_var, value="medium")
        self.medium_radio.pack(side="left", padx=10)
        
        self.low_radio = ctk.CTkRadioButton(self.quality_frame, text="Baja", variable=self.quality_var, value="low")
        self.low_radio.pack(side="left", padx=10)
        
        # Frame para los botones de control
        self.control_frame = ctk.CTkFrame(self.window)
        self.control_frame.pack(pady=10)
        
        # Botón de iniciar/detener
        self.toggle_button = ctk.CTkButton(self.control_frame, text="Detener", command=self.toggle_download)
        self.toggle_button.pack(pady=5)
        
        # Barra de progreso
        self.progress_label = ctk.CTkLabel(self.window, text="")
        self.progress_label.pack(pady=5)
        
        # Frame para los indicadores
        self.indicators_frame = ctk.CTkFrame(self.window)
        self.indicators_frame.pack(pady=5)
        
        # Label para el spinner
        self.spinner_label = ctk.CTkLabel(self.indicators_frame, text="", width=100)
        self.spinner_label.pack(side="left", padx=10)
        
        # Label para el indicador de estado
        self.status_indicator = ctk.CTkLabel(self.indicators_frame, text="⬤", width=30, text_color="orange")
        self.status_indicator.pack(side="left", padx=10)
        
        # Label para mostrar la URL actual
        self.current_url_label = ctk.CTkLabel(self.window, text="", wraplength=500)
        self.current_url_label.pack(pady=5)
        
        # Variables para los indicadores
        self.spinner_state = 0
        self.blink_state = False
        
        # Iniciar los indicadores
        self.update_spinner()
        self.blink_indicator()
        
        # Iniciar el proceso de descarga automática
        self.start_download_thread()
        
        # Bind para detectar nuevas URLs pegadas
        self.url_text.bind('<<Modified>>', self.on_text_modified)
        self.last_content = self.url_text.get("1.0", "end-1c")

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            # First run - ask for download directory
            self.first_run_setup()
        except json.JSONDecodeError:
            # Si el archivo está corrupto, crear uno nuevo
            self.first_run_setup()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def first_run_setup(self):
        messagebox.showinfo("Configuración Inicial", 
                          "Bienvenido! Por favor selecciona el directorio donde se guardarán las descargas.")
        download_dir = filedialog.askdirectory(title="Selecciona directorio de descarga")
        if not download_dir:
            # Si el usuario cancela, usar directorio por defecto
            download_dir = os.path.join("G:", "Mi unidad", "Music")
        
        self.config = {
            'download_path': download_dir
        }
        self.save_config()

    def change_download_dir(self):
        new_dir = filedialog.askdirectory(title="Selecciona nuevo directorio de descarga",
                                        initialdir=self.config['download_path'])
        if new_dir:
            self.config['download_path'] = new_dir
            self.save_config()
            self.dir_label.configure(text=f"Directorio: {new_dir}")
            messagebox.showinfo("Éxito", "Directorio de descarga actualizado")

    def paste_url(self):
        try:
            clipboard = self.window.clipboard_get()
            if clipboard:
                # Dividir el contenido del portapapeles en líneas
                urls = clipboard.split('\n')
                valid_urls = []
                invalid_urls = []
                
                # Validar cada línea
                for url in urls:
                    url = url.strip()
                    if url:  # Si no está vacía
                        if self.is_valid_youtube_url(url):
                            valid_urls.append(url)
                        else:
                            invalid_urls.append(url)
                
                # Si hay URLs válidas, agregarlas
                if valid_urls:
                    current_text = self.url_text.get("1.0", "end-1c")
                    new_content = '\n'.join(valid_urls)
                    if current_text and not current_text.endswith('\n'):
                        new_content = '\n' + new_content
                    self.url_text.insert("end", new_content + '\n')
                
                # Si hay URLs inválidas, mostrar mensaje
                if invalid_urls:
                    messagebox.showwarning(
                        "URLs Inválidas",
                        "Las siguientes líneas no son URLs válidas de YouTube y no se agregarán:\n\n" + 
                        '\n'.join(invalid_urls[:5]) + 
                        ('\n...' if len(invalid_urls) > 5 else '')
                    )
                
                # Si no hay URLs válidas en absoluto
                if not valid_urls and not invalid_urls:
                    messagebox.showinfo("Información", "El portapapeles está vacío")
                
        except Exception as e:
            messagebox.showerror("Error", "Error al acceder al portapapeles")

    def on_text_modified(self, event=None):
        if not self.is_downloading:
            return
            
        current_content = self.url_text.get("1.0", "end-1c")
        if current_content != self.last_content:
            self.last_content = current_content
            self.check_new_urls()
        self.url_text.edit_modified(False)

    def check_new_urls(self):
        content = self.url_text.get("1.0", "end-1c")
        urls = [url.strip() for url in content.split('\n') if url.strip()]
        
        with self.queue_lock:
            current_queue_urls = list(self.download_queue.queue)
            for url in urls:
                if url and self.is_valid_youtube_url(url) and url not in current_queue_urls:
                    print(f"Añadiendo URL a la cola: {url}")
                    self.download_queue.put(url)
                    # Activar inmediatamente el procesamiento si está detenido
                    if not self.is_downloading:
                        self.toggle_download()

    def url_in_queue(self, url):
        with self.queue_lock:
            return url in list(self.download_queue.queue)

    def toggle_download(self):
        if self.is_downloading:
            print("Deteniendo descargas...")
            self.stop_event.set()
            self.toggle_button.configure(text="Iniciar")
            self.is_downloading = False
            self.current_url_label.configure(text="")
            self.spinner_label.configure(text="")
            self.progress_label.configure(text="")
        else:
            print("Iniciando descargas...")
            self.stop_event.clear()
            self.toggle_button.configure(text="Detener")
            self.is_downloading = True
            self.check_new_urls()  # Verificar URLs existentes
            if not self.download_thread or not self.download_thread.is_alive():
                self.start_download_thread()

    def start_download_thread(self):
        if self.download_thread and self.download_thread.is_alive():
            print("El hilo de descarga ya está en ejecución")
            return
            
        self.is_downloading = True
        self.download_thread = threading.Thread(target=self.process_download_queue, daemon=True)
        self.download_thread.start()
        print("Hilo de descarga iniciado")

    def process_download_queue(self):
        while True:  # Bucle infinito
            if self.stop_event.is_set():
                print("Descarga detenida")
                break
                
            try:
                # Intentar obtener una URL de la cola
                url = self.download_queue.get(timeout=1)
                print(f"Procesando URL: {url}")
                
                if self.is_valid_youtube_url(url):
                    try:
                        self.download_single_video(url)
                        self.window.after(0, self.remove_downloaded_url, url)
                    except Exception as e:
                        print(f"Error descargando {url}: {str(e)}")
                        self.window.after(0, lambda: messagebox.showerror("Error", f"Error al descargar {url}: {str(e)}"))
                
            except Empty:
                # Si no hay URLs en la cola, solo continuamos
                continue
            except Exception as e:
                print(f"Error en proceso de descarga: {str(e)}")
                continue
            
            # Marcar la tarea como completada
            self.download_queue.task_done()

    def remove_downloaded_url(self, url):
        try:
            # Obtener el contenido actual
            content = self.url_text.get("1.0", "end-1c")
            lines = content.split('\n')
            
            # Encontrar la línea exacta que contiene la URL
            start_index = "1.0"
            for line in lines:
                if line.strip() == url.strip():
                    # Encontrar la posición exacta de la línea
                    pos = self.url_text.search(line, start_index, "end")
                    if pos:
                        # Obtener el final de la línea
                        line_end = self.url_text.search('\n', pos, "end")
                        if not line_end:
                            # Si es la última línea
                            line_end = "end"
                        else:
                            # Incluir el salto de línea en la eliminación
                            line_end = f"{line_end}+1c"
                        
                        # Eliminar solo esa línea específica
                        self.url_text.delete(pos, line_end)
                        break
                    
            # Eliminar líneas vacías extra
            while True:
                content = self.url_text.get("1.0", "end-1c")
                if content.startswith('\n'):
                    self.url_text.delete("1.0", "2.0")
                elif content.endswith('\n\n'):
                    self.url_text.delete("end-2c", "end-1c")
                else:
                    break
                    
        except Exception as e:
            print(f"Error al eliminar URL: {str(e)}")
            
        # Actualizar el último contenido conocido
        self.last_content = self.url_text.get("1.0", "end-1c")

    def is_valid_youtube_url(self, url):
        youtube_regex = r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[a-zA-Z0-9_-]+(\S*)$'
        return bool(re.match(youtube_regex, url))

    def get_format_options(self):
        format_type = self.format_var.get()
        quality = self.quality_var.get()
        
        if format_type == "mp4":
            if quality == "high":
                return {"format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"}
            elif quality == "medium":
                return {"format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"}
            else:
                return {"format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"}
        else:  # mp3
            if quality == "high":
                return {
                    "format": "bestaudio/best",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }]
                }
            elif quality == "medium":
                return {
                    "format": "bestaudio/best",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }]
                }
            else:
                return {
                    "format": "bestaudio/best",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "128",
                    }]
                }

    def download_progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                self.window.after(0, lambda: self.progress_label.configure(text=f"Descargando: {percent} a {speed}"))
            except Exception as e:
                print(f"Error en progress hook: {str(e)}")  # Debug
        elif d['status'] == 'finished':
            self.window.after(0, lambda: self.progress_label.configure(text="Procesando archivo..."))

    def download_single_video(self, url):
        try:
            # Actualizar la interfaz para mostrar la URL actual
            self.window.after(0, lambda: self.current_url_label.configure(text=f"Descargando: {url}"))
            self.window.after(0, lambda: self.progress_label.configure(text="Iniciando descarga..."))
            print(f"Iniciando descarga de: {url}")
            
            downloads_dir = self.config['download_path']
            os.makedirs(downloads_dir, exist_ok=True)
            
            ydl_opts = self.get_format_options()
            ydl_opts.update({
                "outtmpl": os.path.join(downloads_dir, "%(title)s.%(ext)s"),
                "progress_hooks": [self.download_progress_hook],
                "verbose": True  # Añadir más información de depuración
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"Configuración de descarga: {ydl_opts}")
                ydl.download([url])
            
            print(f"Descarga completada: {url}")
            self.window.after(0, lambda: self.current_url_label.configure(text=""))
            self.window.after(0, lambda: self.progress_label.configure(text=""))
            
        except Exception as e:
            error_msg = f"Error al descargar {url}: {str(e)}"
            print(error_msg)
            self.window.after(0, lambda: messagebox.showerror("Error", error_msg))

    def update_spinner(self):
        if self.is_downloading:
            states = ["   ", ".  ", ".. ", "..."]
            self.spinner_label.configure(text=states[self.spinner_state])
            self.spinner_state = (self.spinner_state + 1) % 4
        else:
            self.spinner_label.configure(text="")
        self.window.after(500, self.update_spinner)

    def blink_indicator(self):
        if not self.is_downloading:
            self.blink_state = not self.blink_state
            self.status_indicator.configure(
                text_color="orange" if self.blink_state else "gray"
            )
        else:
            self.status_indicator.configure(text_color="green")
        self.window.after(800, self.blink_indicator)

    def start_download(self):
        # Iniciar la descarga en un hilo separado
        threading.Thread(target=self.process_download_queue, daemon=True).start()

    def run(self):
        self.window.mainloop()

if __name__ == "__main__":
    app = DownloaderApp()
    app.run()