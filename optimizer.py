import asyncio
from config import config
from optimizer_memory import optimizer_memory

class SmartOptimizer:
    def __init__(self, telemetry_instance):
        self.telemetry = telemetry_instance
        self.min_concurrency = 10
        self.max_concurrency = 1000

        best = optimizer_memory.get_optimal_defaults()
        if best:
            config.total_concurrency = best.get("concurrency", config.total_concurrency)
            config.sleep_min = best.get("sleep_min", config.sleep_min)
            config.sleep_max = best.get("sleep_max", config.sleep_max)
            print(f"[Optimizer] Configuration restaurée : concurrency={config.total_concurrency}, sleep_min={config.sleep_min}, sleep_max={config.sleep_max}")

    async def start_monitoring_loop(self, interval: float = 3.0):
        print("[Optimizer] Boucle d’apprentissage et d’optimisation démarrée.")

        while True:
            # --- 1. Récupération des métriques CPU/RAM ---
            try:
                if hasattr(self.telemetry, "get_latest_metrics") and callable(self.telemetry.get_latest_metrics):
                    metrics = self.telemetry.get_latest_metrics() or {}
                else:
                    metrics = getattr(self.telemetry, "latest_metrics", {}) or {}

                current_cpu = metrics.get("total_cpu_percent", 0.0)
                current_mem = metrics.get("memory_percent", 0.0)
            except Exception as e:
                print(f"[Optimizer] Impossible de lire les métriques système : {e}")
                await asyncio.sleep(interval)
                continue

            # --- 2. Calcul des vrais taux de requêtes et de blocage ---
            try:
                reqs = getattr(config, "total_requests", 0)
                blocks = getattr(config, "blocked_requests", 0)
                
                if reqs > 0:
                    block_rate = min(1.0, blocks / reqs)
                    success_score = max(0.0, 100.0 - (block_rate * 100.0))
                else:
                    block_rate = 0.0
                    success_score = 100.0

                # Remise à zéro pour le prochain cycle de 3 secondes
                config.total_requests = 0
                config.blocked_requests = 0
            except Exception as e:
                block_rate = 0.0
                success_score = 100.0
                config.total_requests = 0
                config.blocked_requests = 0

            # --- 3. Apprentissage à partir du dataset avant l'ajustement en direct ---
            try:
                self._apply_history_based_learning()
            except Exception as e:
                print(f"[Optimizer] Échec de l’apprentissage à partir de l’historique : {e}")

            # --- 4. Ajustement basé sur le CPU/RAM ET les blocages ---
            try:
                self._evaluate_and_adjust(current_cpu, current_mem, block_rate)
            except Exception as e:
                print(f"[Optimizer] Échec de l’ajustement des paramètres : {e}")

            # --- 5. Sauvegarde dans le dataset ---
            try:
                optimizer_memory.record_run(
                    concurrency=config.total_concurrency,
                    sleep_min=config.sleep_min,
                    sleep_max=config.sleep_max,
                    success_score=success_score,
                    block_rate=block_rate
                )
            except Exception as e:
                print(f"[Optimizer] Échec de la sauvegarde du dataset : {e}")

            await asyncio.sleep(interval)

    def _apply_history_based_learning(self):
        recommendation = optimizer_memory.get_learning_recommendation(lookback=20)
        if not recommendation:
            return

        target_concurrency = int(recommendation.get("concurrency", config.total_concurrency))
        if target_concurrency > 0:
            blended_concurrency = int(config.total_concurrency * 0.85 + target_concurrency * 0.15)
            config.total_concurrency = max(self.min_concurrency, min(self.max_concurrency, blended_concurrency))

        target_sleep_min = float(recommendation.get("sleep_min", config.sleep_min))
        target_sleep_max = float(recommendation.get("sleep_max", config.sleep_max))

        if target_sleep_min > 0:
            config.sleep_min = round(config.sleep_min + (target_sleep_min - config.sleep_min) * 0.15, 3)
        if target_sleep_max > 0:
            config.sleep_max = round(config.sleep_max + (target_sleep_max - config.sleep_max) * 0.15, 3)

        print(
            f"[Optimizer] Réglage appris à partir de l’historique -> concurrency={config.total_concurrency}, "
            f"sleep_min={config.sleep_min}, sleep_max={config.sleep_max}"
        )

    def _evaluate_and_adjust(self, cpu: float, memory: float, block_rate: float):
        if block_rate > 0.02:
            print(f"[Optimizer] Blocage détecté à {block_rate*100:.1f}% : ralentissement de la cadence appliqué.")
            config.total_concurrency = max(self.min_concurrency, int(config.total_concurrency * 0.85))
            config.sleep_min = min(5.0, config.sleep_min + 0.2)
            config.sleep_max = min(10.0, config.sleep_max + 0.4)
            return

        if cpu >= config.SAFE_CPU_LOCK or memory >= config.SAFE_MEMORY_LOCK:
            print(f"[Optimizer] Limite système atteinte (CPU: {cpu:.1f}% / RAM: {memory:.1f}%) : réduction de la charge appliquée.")
            config.total_concurrency = max(self.min_concurrency, int(config.total_concurrency * 0.85))
            config.sleep_min = min(5.0, config.sleep_min + 0.2)
            config.sleep_max = min(10.0, config.sleep_max + 0.4)
            return

        if cpu >= 70.0 or memory >= 70.0:
            print(f"[Optimizer] Ressources stables (CPU: {cpu:.1f}% | RAM: {memory:.1f}% | concurrency: {config.total_concurrency})")
            return

        if cpu < 70.0 and memory < 70.0 and block_rate == 0.0:
            if config.total_concurrency < self.max_concurrency:
                increment = 5 if config.total_concurrency > 300 else 15
                config.total_concurrency = min(self.max_concurrency, config.total_concurrency + increment)
            
            if config.sleep_min > 0.3:
                config.sleep_min = max(0.2, config.sleep_min - 0.05)
            if config.sleep_max > 0.6:
                config.sleep_max = max(0.4, config.sleep_max - 0.05)
                
            print(f"[Optimizer] Système sain : augmentation progressive de la charge (concurrency: {config.total_concurrency})")