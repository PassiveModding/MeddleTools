from . import setup

def register():
    setup.register()
        

def unregister():
    setup.unregister()

if __name__ == "__main__":
    register()