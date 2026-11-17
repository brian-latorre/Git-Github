import random

def estimar_pi(total_puntos: int) -> float:
    puntos_dentro = 0
    for _ in range(total_puntos):
        x = random.uniform(0, 1)
        y = random.uniform(0, 1)
        # El radio al cuadrado de la circunferencia unitaria es 1
        if x**2 + y**2 <= 1.0:
            puntos_dentro += 1
            
    pi_estimado: float = (puntos_dentro / total_puntos) * 4.0
    return pi_estimado


print(estimar_pi(1000000))