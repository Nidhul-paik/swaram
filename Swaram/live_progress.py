# Swaram/live_progress.py
import json
import time
from django.conf import settings
from pathlib import Path

class LiveProgressTracker:
    def __init__(self):
        self.progress_file = Path(settings.BASE_DIR) / 'live_progress.json'
        self.user_timeout = 300  # 5 minutes - consider user inactive after this
    
    def get_live_progress(self):
        """Get progress of currently active users"""
        try:
            if not self.progress_file.exists():
                return self._get_empty_progress()
            
            with open(self.progress_file, 'r') as f:
                data = json.load(f)
            
            # Filter only active users (users who saved in last 5 minutes)
            current_time = time.time()
            active_users = {}
            total_saved = 0
            total_files = 0
            
            for username, user_data in data.get('users', {}).items():
                if current_time - user_data.get('last_save', 0) <= self.user_timeout:
                    active_users[username] = user_data
                    total_saved += user_data.get('saved_count', 0)
                    total_files += user_data.get('total_files', 0)
            
            # Calculate percentages
            active_count = len(active_users)
            overall_percentage = round((total_saved / total_files * 100) if total_files > 0 else 0, 1)
            
            # Sort active users by save count
            sorted_users = sorted(active_users.items(), 
                                key=lambda x: x[1].get('saved_count', 0), 
                                reverse=True)
            
            return {
                'active_users_count': active_count,
                'total_saved': total_saved,
                'total_files': total_files,
                'overall_percentage': overall_percentage,
                'active_users': [
                    {
                        'username': username,
                        'saved_count': data.get('saved_count', 0),
                        'total_files': data.get('total_files', 0),
                        'percentage': round((data.get('saved_count', 0) / data.get('total_files', 1) * 100), 1),
                        'last_active': self._format_time(current_time - data.get('last_save', 0))
                    }
                    for username, data in sorted_users
                ],
                'timestamp': current_time,
                'message': self._get_progress_message(active_count, overall_percentage)
            }
            
        except Exception as e:
            print(f"Error reading live progress: {e}")
            return self._get_empty_progress()
    
    def record_save_action(self, username, total_files):
        """Record when a user clicks save"""
        try:
            # Load existing data
            if self.progress_file.exists():
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'users': {}}
            
            # Initialize or update user data
            if username not in data['users']:
                data['users'][username] = {
                    'saved_count': 0,
                    'total_files': total_files,
                    'last_save': time.time()
                }
            
            # Increment save count and update timestamp
            user_data = data['users'][username]
            user_data['saved_count'] = user_data.get('saved_count', 0) + 1
            user_data['last_save'] = time.time()
            user_data['total_files'] = total_files  # Update total files
            
            # Save back to file
            with open(self.progress_file, 'w') as f:
                json.dump(data, f)
                
            print(f"📝 Recorded save for {username}: {user_data['saved_count']}/{total_files}")
            
        except Exception as e:
            print(f"Error recording save action: {e}")
    
    def _format_time(self, seconds):
        """Format time since last activity"""
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{int(seconds/60)}m ago"
        else:
            return f"{int(seconds/3600)}h ago"
    
    def _get_progress_message(self, active_users, percentage):
        if active_users == 0:
            return "👋 No active verifiers"
        elif percentage >= 80:
            return f"🎉 {active_users} users verifying - Almost done!"
        elif percentage >= 50:
            return f"🚀 {active_users} active verifiers - Great progress!"
        elif percentage >= 20:
            return f"🔥 {active_users} users working - Keep it up!"
        else:
            return f"⭐ {active_users} verifiers active - Good start!"
    
    def _get_empty_progress(self):
        return {
            'active_users_count': 0,
            'total_saved': 0,
            'total_files': 0,
            'overall_percentage': 0,
            'active_users': [],
            'timestamp': time.time(),
            'message': "👋 No active verifiers"
        }

# Global instance
live_tracker = LiveProgressTracker()