import os 
import importlib

def iniciar_sistema():

    print("Iniciando sistema...")    
    archivos = [f[:-3] for f in os.listdir("app/modulos") if f.endswith(".py")]
    if not archivos: 
        print("No se implementaron modulos")
        return
    for nombre_modulo in archivos:

        print(f"Iniciando módulo: {nombre_modulo}")
        try:
            modulo = importlib.import_module(f"app.modulos.{nombre_modulo}")
            modulo.ejecutar()
        except Exception as e:
            print(f"Error al iniciar el módulo {nombre_modulo}: {e}")

if __name__ == "__main__":
    iniciar_sistema()