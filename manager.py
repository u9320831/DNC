import time
import threading
from collections import deque

class AdaptiveManager:
    def __init__(self, tor_pool, initial_jitter=(0.2, 0.5), evaluation_interval=5):
        self.tor_pool = tor_pool
        self.min_jitter, self.max_jitter = initial_jitter
        self.evaluation_interval = evaluation_interval
        
        self.metrics_history = deque(maxlen=300)
        self.instance_stats = {} 
        
        self.lock = threading.Lock()
        self.is_running = True
        
        self.monitor_thread = threading.Thread(target=self._regulation_loop, daemon=True)
        self.monitor_thread.start()

    def record_result(self, instance_id, status_code, response_time):
        with self.lock:
            if instance_id not in self.instance_stats:
                self.instance_stats[instance_id] = {
                    'success': 0, 
                    'errors': 0, 
                    'blocked': 0, 
                    'response_times': deque(maxlen=50)
                }
            
            stats = self.instance_stats[instance_id]
            self.metrics_history.append((instance_id, status_code, response_time))
            
            # Catégorisation du résultat
            if status_code == 200:
                stats['success'] += 1
                stats['response_times'].append(response_time)
            elif status_code in [429, 403]: 
                stats['blocked'] += 1
            else:
                stats['errors'] += 1

    def _calculate_efficiency(self, stats):
        total = stats['success'] + stats['errors'] + stats['blocked']
        if total == 0:
            return 1.0
        
        score = (stats['success'] * 1.0 - stats['blocked'] * 3.0 - stats['errors'] * 0.5) / total
        return max(0.0, score)

    def _regulation_loop(self):
        while self.is_running:
            time.sleep(self.evaluation_interval)
            
            with self.lock:
                if not self.metrics_history:
                    continue
                
                recent_blocked = sum(1 for _, code, _ in self.metrics_history if code in [429, 403])
                total_recent = len(self.metrics_history)
                error_rate = recent_blocked / total_recent if total_recent > 0 else 0
                
                if error_rate > 0.04: 
                    self.min_jitter = min(self.min_jitter * 1.4, 4.0)
                    self.max_jitter = min(self.max_jitter * 1.4, 8.0)
                    print(f"[Manager Adaptive] Rate-limit détecté ({error_rate:.2%}). Ralentissement -> Jitter : [{self.min_jitter:.2f}s, {self.max_jitter:.2f}s]")
                elif error_rate < 0.005 and self.min_jitter > 0.15:  
                    self.min_jitter = max(self.min_jitter * 0.9, 0.1)
                    self.max_jitter = max(self.max_jitter * 0.9, 0.3)
                
                for inst_id, stats in self.instance_stats.items():
                    efficiency = self._calculate_efficiency(stats)
                    
                    if efficiency < 0.4 or stats['blocked'] >= 4:
                        print(f"[Manager] Instance Tor {inst_id} sous-performante ou saturée (efficacité: {efficiency:.2f}). Rotation de circuit forcée.")
                        
                        if self.tor_pool and hasattr(self.tor_pool, 'renew_instance'):
                            self.tor_pool.renew_instance(inst_id)
                        
                        stats['success'] = 0
                        stats['errors'] = 0
                        stats['blocked'] = 0

    def get_current_jitter(self):
        with self.lock:
            return self.min_jitter, self.max_jitter

    def stop(self):
        self.is_running = False