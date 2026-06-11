"""Overlay de seleção de região de captura.

Abre uma janela fullscreen semi-transparente onde o usuário
arrasta o mouse para desenhar um retângulo e definir a área
de captura de legendas.
"""
import tkinter as tk


class RegionSelector:
    """Janela overlay para selecionar região da tela via arrasto.

    Uso:
        selector = RegionSelector()
        region = selector.select()
        # region = {"top": ..., "left": ..., "width": ..., "height": ...}
    """

    def __init__(self):
        self._result: dict | None = None
        self._start_x = None
        self._start_y = None
        self._rect_id = None

    def select(self) -> dict:
        """Abre a overlay e retorna a região selecionada.

        Returns:
            Dict com top, left, width, height.
        """
        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.3)
        root.attributes("-topmost", True)
        root.configure(cursor="crosshair", bg="black")

        canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)

        instr = tk.Label(
            root,
            text="Arraste para definir a região · ESC para cancelar · Enter para confirmar",
            bg="black", fg="white",
            font=("Segoe UI", 14),
        )
        instr.place(relx=0.5, rely=0.95, anchor="s")

        def on_press(event):
            self._start_x = event.x
            self._start_y = event.y
            if self._rect_id:
                canvas.delete(self._rect_id)
            self._rect_id = canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#4caf50", width=3, fill="",
            )

        def on_drag(event):
            if self._rect_id and self._start_x is not None:
                canvas.coords(
                    self._rect_id, self._start_x, self._start_y, event.x, event.y
                )

        def on_release(event):
            if self._start_x is not None and self._start_y is not None:
                x1, y1 = min(self._start_x, event.x), min(self._start_y, event.y)
                x2, y2 = max(self._start_x, event.x), max(self._start_y, event.y)
                if x2 - x1 > 10 and y2 - y1 > 10:
                    self._result = {
                        "top": y1,
                        "left": x1,
                        "width": x2 - x1,
                        "height": y2 - y1,
                    }

        def on_confirm(event=None):
            if self._result:
                root.destroy()

        def on_cancel(event=None):
            self._result = None
            root.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind("<Escape>", on_cancel)
        root.bind("<Return>", on_confirm)

        root.mainloop()

        if self._result is None:
            return {"top": 0, "left": 50, "width": 1820, "height": 80}

        return self._result
