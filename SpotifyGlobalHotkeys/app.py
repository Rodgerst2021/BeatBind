import os
import sys
import json
import time
import win32api
import win32con
import win32gui
import requests
import threading
import json.decoder
import winreg as reg
import tkinter.messagebox as messagebox
from spotipy.oauth2 import SpotifyOAuth
from pynput import keyboard

class SpotifyGlobalHotkeysApp(object):
    def __init__(self):
        def resource_path(relative_path):
            if getattr(sys, 'frozen', False):
                # running as an application
                base_path = sys._MEIPASS
            else:
                # running as a standalone script
                base_path = os.path.dirname(os.path.abspath(__file__))
            return os.path.join(base_path, relative_path)
        
        # Create paths
        self.app_folder = os.path.join(os.environ['APPDATA'], '.spotify_global_hotkeys')
        os.makedirs(self.app_folder, exist_ok=True)
        self.config_path = os.path.join(self.app_folder, 'config.json')
        self.icon_path = resource_path('icon.ico')
       
        # Spotify credentials
        self.username = None
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None
        self.device_id = None
        self.scope = 'user-modify-playback-state,user-read-playback-state'

        # Global hotkeys
        self.hotkeys = {
            'play/pause': None,
            'prev_track': None,
            'next_track': None,
            'volume_up': None,
            'volume_down': None
        }
        self.play_pause_hotkey = None
        self.prev_track_hotkey = None
        self.next_track_hotkey = None
        self.volume_up_hotkey = None
        self.volume_down_hotkey = None
        self.last_volume = None
        
        # Startup and minimize
        self.startup_var = None
        self.minimize_var = None

        # Spotify access token
        self.auth_manager = None
        self.token_data = None
        self.token = None
        self.expires_in = None
        
        # Thread flags
        self.refresh_thread_running = False
        
        # Set up wake-up event listener
        app_class = win32gui.WNDCLASS()
        app_class.lpfnWndProc = self.WndProc
        app_class.lpszClassName = "SpotifyGlobalHotkeysApp"
        app_class.hInstance = win32api.GetModuleHandle()
        class_atom = win32gui.RegisterClass(app_class)
        self.hwnd = win32gui.CreateWindowEx(0, class_atom, None, 0, 0, 0, 0, 0, None, None, app_class.hInstance, None)
        
    # --------------------------------------------------------------------------------------- #
    '''
    API
    '''
    def RefreshToken(self):
        while True:
            time.sleep(self.expires_in - 60)  # Sleep until the token needs to be refreshed
            print('Refreshing token')
            self.token_data = self.auth_manager.refresh_access_token(self.auth_manager.get_cached_token()['refresh_token'])
            self.token = self.token_data['access_token']
            self.expires_in = self.token_data['expires_in']
            
    def CreateToken(self):
        print('Creating token')
        cache_file = os.path.join(self.app_folder, f'.cache-{self.username}')
        try:
            self.auth_manager = SpotifyOAuth(username=self.username,
                                            scope=self.scope,
                                            client_id=self.client_id,
                                            client_secret=self.client_secret,
                                            redirect_uri=self.redirect_uri,
                                            cache_path=cache_file)
        except:
            self.ErrorMessage('Invalid credentials. Please check your input fields.')
            return False
        
        try:
            self.token_data = self.auth_manager.refresh_access_token(self.auth_manager.get_cached_token()['refresh_token'])
        except:
            self.token_data = self.auth_manager.get_access_token()

        self.token = self.token_data['access_token']
        self.expires_in = self.token_data['expires_in']

        # Start the loop to refresh the token before it expires, if not already running
        if not self.refresh_thread_running:
            print('Created refresh thread')
            refresh_thread = threading.Thread(target=self.RefreshToken)
            refresh_thread.daemon = True
            refresh_thread.start()
            self.refresh_thread_running = True
            
        return True
              
    def HandleConnectionError(self, retry_count=0):
        # Connection error occurs when device is no longer active, so play music on specific device id
        headers = {'Authorization': 'Bearer ' + self.token}
        url = f'https://api.spotify.com/v1/me/player/play?device_id={self.device_id}'
        try:
            response = requests.put(url, headers=headers)
            if response.status_code == 403:  # The music is already playing
                # pause music on specific device id
                url = f'https://api.spotify.com/v1/me/player/pause?device_id={self.device_id}'
                response = requests.put(url, headers=headers)
                response.raise_for_status()
                print('Paused music')
                return
            response.raise_for_status()
            print('Playing music')
        except Exception as e:
            print(f'Error: {e}')
 
    def PlayPause(self):
        is_playing = self.GetPlaybackState()
        if is_playing is None:
            return

        headers = {'Authorization': 'Bearer ' + self.token}
        if is_playing:
            # Pause the music
            url = f'https://api.spotify.com/v1/me/player/pause?device_id={self.device_id}'
        else:
            # Play the music
            url = f'https://api.spotify.com/v1/me/player/play?device_id={self.device_id}'
        try:
            response = requests.put(url, headers=headers)
            response.raise_for_status()
            if is_playing:
                print('Paused music')
            else:
                print('Playing music')
        except Exception as e:
            print(f'Error: {e}')
            
    def PrevNext(self, command):
        headers = {'Authorization': 'Bearer ' + self.token}
        url = f'https://api.spotify.com/v1/me/player/{command}?device_id={self.device_id}'
        try:
            response = requests.post(url, headers=headers)
            response.raise_for_status()
            if command == 'previous':
                print('Previous track')
            else:
                print('Next track')
        except Exception as e:
            print(f'Error: {e}')

    def AdjustVolume(self, amount):
        headers = {'Authorization': 'Bearer ' + self.token}
        self.last_volume = self.GetCurrentVolume()
        url = f'https://api.spotify.com/v1/me/player/volume?volume_percent={self.last_volume + amount}&device_id={self.device_id}'
        try:
            response = requests.put(url, headers=headers)
            response.raise_for_status()
            if amount > 0:
                print('Volume up')
            else:
                print('Volume down')
        except Exception as e:
            print(f'Error: {e}')

    def GetCurrentVolume(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        url = 'https://api.spotify.com/v1/me/player'
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            volume = data['device']['volume_percent']
            if (volume + 5) > 100:
                return 95
            elif (volume - 5) < 0:
                return 5
            return volume
        except Exception as e:
            print(f'Error: {e}')
            return self.last_volume
        
    def GetPlaybackState(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        url = 'https://api.spotify.com/v1/me/player'
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            playback_data = response.json()
            return playback_data['is_playing']
        except Exception as e:
            print(f'Error fetching playback state: {e}')
            self.HandleConnectionError()
            return None
        
    # --------------------------------------------------------------------------------------- #
    '''
    MISC
    '''
    def ErrorMessage(self, message):
        messagebox.showerror("Error", message)
        
    def WndProc(self, hWnd, message, wParam, lParam):
        if message == win32con.WM_POWERBROADCAST:
            if wParam == win32con.PBT_APMRESUMEAUTOMATIC:  # System is waking up from sleep
                print("System woke up from sleep")
                self.CreateToken()
        return win32gui.DefWindowProc(hWnd, message, wParam, lParam)
    
    def UpdateStartupRegistry(self):
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_name = 'SpotifyGlobalHotkeys'
        exe_path = os.path.realpath(sys.argv[0])
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_ALL_ACCESS)
        
        try:
            registry_value, _ = reg.QueryValueEx(key, app_name)
            if registry_value != exe_path:
                reg.SetValueEx(key, app_name, 0, reg.REG_SZ, exe_path)
        except FileNotFoundError:
            print('Could not find the startup registry key')

        reg.CloseKey(key)

    def SetStartup(self, enabled):
        key = reg.HKEY_CURRENT_USER
        sub_key = r'Software\Microsoft\Windows\CurrentVersion\Run'
        app_name = 'SpotifyGlobalHotkeys'

        with reg.OpenKey(key, sub_key, 0, reg.KEY_ALL_ACCESS) as reg_key:
            if enabled:
                exe_path = os.path.realpath(sys.argv[0])
                reg.SetValueEx(reg_key, app_name, 0, reg.REG_SZ, exe_path)
            else:
                try:
                    reg.DeleteValue(reg_key, app_name)
                except FileNotFoundError:
                    pass
    
    def HotkeyListener(self):
        print('Listening to hotkeys...')
        
        def with_cooldown(func):
            last_called = [0]
            def wrapper(*args, **kwargs):
                if time.time() - last_called[0] > 0.3:  # 0.3 seconds cooldown
                    func(*args, **kwargs)
                    last_called[0] = time.time()
            return wrapper

        listener = keyboard.GlobalHotKeys({
            self.hotkeys['play/pause']: with_cooldown(lambda: self.PlayPause()),
            self.hotkeys['prev_track']: with_cooldown(lambda: self.PrevNext('previous')),
            self.hotkeys['next_track']: with_cooldown(lambda: self.PrevNext('next')),
            self.hotkeys['volume_up']: with_cooldown(lambda: self.AdjustVolume(5)),
            self.hotkeys['volume_down']: with_cooldown(lambda: self.AdjustVolume(-5))
        })
        listener.start()
            
    def SaveConfig(self):
        print('Saving config')
        # Add the hotkeys to the config dictionary
        config = {
            'startup': self.startup_var.get(),
            'minimize': self.minimize_var.get(),
            'username': self.username,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'device_id': self.device_id,
            'hotkeys': self.hotkeys
        }
        try:
            # Save the config to the file
            with open(self.config_path, 'w') as f:
                json.dump(config, f)
        except IOError as e:
            print(f'Error saving config: {e}')
        except Exception as e:
            print(f'Unexpected error while saving config: {e}')