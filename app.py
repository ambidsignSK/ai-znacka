"""AI značka – desktopová aplikácia na zápis značky „Generated AI“ do metadát obrázkov."""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core
import updater
from version import VERSION

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # aplikácia funguje aj bez drag & drop
    TkinterDnD = None

EXTS = (".jpg", ".jpeg", ".png", ".webp")
APP_NAME = "AI značka"
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "AI_oznacene")


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def to_recycle_bin(paths):
    """Presunie súbory do Koša (Windows). Inde ich zmaže."""
    if sys.platform != "win32":
        for p in paths:
            os.remove(p)
        return
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT = 3, 0x40, 0x10, 0x4
    op = SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom="\0".join(paths) + "\0\0",
                         fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT)
    if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) or op.fAnyOperationsAborted:
        raise OSError("Windows nepresunul všetky súbory do Koša.")


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", path])


class App:
    def __init__(self, root):
        self.root = root
        self.files = []  # cesty v poradí, ako boli pridané
        self.last_dir = None
        self.saved = {}  # originál -> stiahnutá upravená kópia
        root.title(f"{APP_NAME} – verzia {VERSION}" if VERSION else APP_NAME)
        root.geometry("940x660")
        root.minsize(760, 500)
        try:
            root.iconbitmap(resource("ikona.ico"))
        except tk.TclError:
            pass

        self.var_on = tk.BooleanVar(value=True)
        self.var_type = tk.StringVar(value="trainedAlgorithmicMedia")
        self.var_label = tk.StringVar(value=core.DEFAULT_LABEL)
        self.var_tool = tk.StringVar()
        self.var_out = tk.StringVar(value="folder")
        self.var_dir = tk.StringVar(value=DEFAULT_DIR)

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=24)
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))

        main = ttk.Frame(root, padding=12)
        main.pack(fill="both", expand=True)

        # --- nastavenia
        box = ttk.LabelFrame(main, text="Nastavenia", padding=10)
        box.pack(fill="x")
        box.columnconfigure(3, weight=1)
        ttk.Checkbutton(box, text="Zapísať označenie AI do metadát", variable=self.var_on,
                        command=self.sync).grid(row=0, column=0, columnspan=4, sticky="w")
        self.lbl_switch = ttk.Label(box, foreground="#555")
        self.lbl_switch.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.opts = []
        for i, (key, text) in enumerate(core.TYPES.items()):
            w = ttk.Radiobutton(box, text=text, value=key, variable=self.var_type)
            w.grid(row=2 + i, column=0, columnspan=2, sticky="w")
            self.opts.append(w)
        ttk.Label(box, text="Text značky:").grid(row=2, column=2, sticky="e", padx=(24, 6))
        e1 = ttk.Entry(box, textvariable=self.var_label, width=28)
        e1.grid(row=2, column=3, sticky="w")
        ttk.Label(box, text="AI nástroj (voliteľné):").grid(row=3, column=2, sticky="e", padx=(24, 6))
        e2 = ttk.Entry(box, textvariable=self.var_tool, width=28)
        e2.grid(row=3, column=3, sticky="w")
        self.opts += [e1, e2]

        out = ttk.LabelFrame(main, text="Kam stiahnuť upravené obrázky", padding=10)
        out.pack(fill="x", pady=(10, 0))
        out.columnconfigure(1, weight=1)
        ttk.Radiobutton(out, text="do priečinka:", value="folder", variable=self.var_out).grid(row=0, column=0, sticky="w")
        ttk.Entry(out, textvariable=self.var_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(out, text="Zmeniť…", command=self.pick_out_dir).grid(row=0, column=2)
        ttk.Radiobutton(out, text="prepísať pôvodné súbory", value="overwrite",
                        variable=self.var_out).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # --- tlačidlá na pridanie
        bar = ttk.Frame(main)
        bar.pack(fill="x", pady=10)
        ttk.Button(bar, text="Pridať obrázky…", command=self.pick_files).pack(side="left")
        ttk.Button(bar, text="Pridať priečinok…", command=self.pick_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Odstrániť vybrané", command=self.remove_selected).pack(side="left")
        ttk.Button(bar, text="Vymazať zoznam", command=self.clear).pack(side="left", padx=6)

        # --- tlačidlá na stiahnutie (dole)
        actions = ttk.Frame(main)
        actions.pack(fill="x", side="bottom", pady=(10, 0))
        ttk.Button(actions, text="Stiahnuť všetky", style="Big.TButton",
                   command=self.save_all).pack(side="right")
        ttk.Button(actions, text="Stiahnuť vybraný ako…", command=self.save_selected_as).pack(side="right", padx=6)
        self.btn_open = ttk.Button(actions, text="Otvoriť priečinok so stiahnutými", command=self.open_out)
        self.btn_open.pack(side="left")
        ttk.Button(actions, text="Zmazať originály", command=self.delete_originals).pack(side="right", padx=(0, 18))
        self.btn_update = ttk.Button(actions, text="Aktualizovať", command=self.update_app)
        self.btn_update.pack(side="left", padx=6)

        # --- zoznam
        cols = ("file", "fmt", "before", "result")
        frame = ttk.Frame(main)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for c, t, w in (("file", "Súbor", 260), ("fmt", "Formát", 70),
                        ("before", "AI značka v súbore", 150), ("result", "Stav", 400)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w", stretch=(c in ("file", "result")))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<Double-1>", self.show_meta)
        self.tree.bind("<Delete>", self.remove_selected)
        self.tree.bind("<Button-3>", self.context_menu)

        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Stiahnuť ako…", command=self.save_selected_as)
        self.menu.add_command(label="Zobraziť metadáta", command=self.show_meta)
        self.menu.add_command(label="Zmazať originál (do Koša)", command=self.delete_originals)
        self.menu.add_separator()
        self.menu.add_command(label="Odstrániť zo zoznamu", command=self.remove_selected)

        self.status = ttk.Label(root, padding=(12, 4), anchor="w")
        self.status.pack(fill="x", side="bottom")

        if TkinterDnD is not None:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", lambda e: self.add(root.tk.splitlist(e.data)))
        self.sync()
        self.set_status()
        if updater.is_exe():  # potichu zistí, či je nová verzia, a zvýrazní tlačidlo
            threading.Thread(target=self.check_update_quietly, daemon=True).start()

    # ------------------------------------------------------------ zoznam
    def set_status(self, text=None):
        if text is None:
            hint = "Pretiahni obrázky sem alebo použi „Pridať obrázky…“." if TkinterDnD else "Použi „Pridať obrázky…“."
            text = f"Súbory: {len(self.files)}. {hint} Pravý klik na riadok = ďalšie možnosti."
        self.status.configure(text=text)

    def sync(self):
        on = self.var_on.get()
        for w in self.opts:
            w.state(["!disabled"] if on else ["disabled"])
        self.lbl_switch.configure(text="Zapnuté: do stiahnutých súborov sa zapíše značka AI." if on
                                  else "Vypnuté: stiahneš presnú kópiu originálu, bez zmeny.")

    def add(self, paths):
        found = []
        for p in paths:
            if os.path.isdir(p):
                for name in sorted(os.listdir(p)):
                    full = os.path.join(p, name)
                    if os.path.isfile(full) and name.lower().endswith(EXTS):
                        found.append(full)
            elif os.path.isfile(p) and p.lower().endswith(EXTS):
                found.append(p)
        for p in found:
            p = os.path.abspath(p)
            if p in self.files:
                continue
            self.files.append(p)
            try:
                with open(p, "rb") as f:
                    data = f.read()
                values = (os.path.basename(p), core.scan(data)["fmt"], core.ai_label(data) or "—", "pripravené na stiahnutie")
            except (OSError, core.MarkError) as e:
                values = (os.path.basename(p), "", "chyba", str(e))
            self.tree.insert("", "end", iid=p, values=values)
        self.set_status()

    def pick_files(self):
        paths = filedialog.askopenfilenames(title="Vyber obrázky",
                                            filetypes=[("Obrázky", "*.jpg *.jpeg *.png *.webp"), ("Všetky súbory", "*.*")])
        self.add(paths)

    def pick_folder(self):
        p = filedialog.askdirectory(title="Vyber priečinok s obrázkami")
        if p:
            self.add([p])

    def pick_out_dir(self):
        p = filedialog.askdirectory(title="Kam ukladať upravené obrázky", initialdir=self.var_dir.get())
        if p:
            self.var_dir.set(os.path.normpath(p))
            self.var_out.set("folder")

    def clear(self):
        self.files.clear()
        self.tree.delete(*self.tree.get_children())
        self.set_status()

    def remove_selected(self, _e=None):
        for iid in self.tree.selection():
            self.forget(iid)
        self.set_status()

    def forget(self, path):
        self.tree.delete(path)
        self.files.remove(path)
        self.saved.pop(path, None)

    def delete_originals(self):
        """Presunie do Koša pôvodné súbory, z ktorých už existuje stiahnutá kópia."""
        rows = self.tree.selection() or tuple(self.files)
        done = [p for p in rows
                if p in self.saved and os.path.normcase(self.saved[p]) != os.path.normcase(p)
                and os.path.isfile(self.saved[p]) and os.path.isfile(p)]
        if not done:
            messagebox.showinfo(APP_NAME, "Nie je čo zmazať. Originál sa dá zmazať až potom, "
                                          "ako si stiahneš jeho upravenú kópiu.")
            return
        skipped = len(rows) - len(done)
        msg = f"Presunúť do Koša {len(done)} pôvodných obrázkov?\n\nUpravené kópie zostanú v:\n{self.var_dir.get()}"
        if skipped:
            msg += f"\n\n{skipped} obrázkov sa nezmaže, lebo ešte nemajú stiahnutú kópiu."
        if not messagebox.askyesno(APP_NAME, msg):
            return
        try:
            to_recycle_bin([os.path.normpath(p) for p in done])
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Mazanie sa nepodarilo: {e}")
        gone = [p for p in done if not os.path.exists(p)]
        for p in gone:
            self.forget(p)
        self.set_status(f"Do Koša presunutých originálov: {len(gone)}. Upravené kópie zostali.")

    def context_menu(self, e):
        row = self.tree.identify_row(e.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.tree.focus(row)
            self.menu.tk_popup(e.x_root, e.y_root)

    # ------------------------------------------------------------ ukladanie
    def produce(self, path):
        with open(path, "rb") as f:
            data = f.read()
        if not self.var_on.get():
            return data
        return core.mark(data, self.var_type.get(), self.var_label.get(), self.var_tool.get())

    def write(self, src, target):
        out = self.produce(src)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, target)
        after = core.ai_label(out)
        state = f"Označené ({after})" if self.var_on.get() else "Kópia bez zmeny"
        self.tree.set(src, "result", f"{state} → {target}")
        self.saved[src] = target
        if os.path.normcase(target) == os.path.normcase(src):
            self.tree.set(src, "before", after or "—")
        self.last_dir = os.path.dirname(target)

    def save_all(self):
        if not self.files:
            messagebox.showinfo(APP_NAME, "Najprv pridaj obrázky.")
            return
        overwrite = self.var_out.get() == "overwrite"
        if overwrite and not self.var_on.get():
            messagebox.showinfo(APP_NAME, "Prepínač je vypnutý, pôvodné súbory by sa nezmenili.")
            return
        if overwrite and not messagebox.askyesno(APP_NAME, "Naozaj prepísať pôvodné súbory?"):
            return
        folder = self.var_dir.get().strip()
        if not overwrite and not folder:
            messagebox.showinfo(APP_NAME, "Vyber priečinok, kam sa majú obrázky stiahnuť.")
            return
        ok = err = 0
        for p in self.files:
            target = p if overwrite else os.path.join(folder, os.path.basename(p))
            if not overwrite and os.path.normcase(os.path.abspath(target)) == os.path.normcase(p):
                self.tree.set(p, "result", "Chyba: cieľový priečinok je ten istý ako originál – zvoľ iný.")
                err += 1
                continue
            try:
                self.write(p, target)
                ok += 1
            except (OSError, core.MarkError) as e:
                self.tree.set(p, "result", f"Chyba: {e}")
                err += 1
            self.root.update_idletasks()
        self.set_status(f"Hotovo: stiahnutých {ok}" + (f", {err} s chybou." if err else "."))
        if ok and not overwrite and messagebox.askyesno(APP_NAME, f"Stiahnutých obrázkov: {ok}\n\n{folder}\n\nOtvoriť priečinok?"):
            self.open_out()

    def save_selected_as(self):
        sel = self.tree.selection() or ((self.tree.focus(),) if self.tree.focus() else ())
        if not sel:
            messagebox.showinfo(APP_NAME, "Najprv klikni v zozname na obrázok, ktorý chceš stiahnuť.")
            return
        if len(sel) > 1:
            folder = filedialog.askdirectory(title=f"Kam stiahnuť {len(sel)} obrázkov",
                                             initialdir=self.var_dir.get())
            if not folder:
                return
            targets = [(p, os.path.join(folder, os.path.basename(p))) for p in sel]
        else:
            p = sel[0]
            name = os.path.basename(p)
            ext = os.path.splitext(name)[1]
            if self.var_dir.get():
                os.makedirs(self.var_dir.get(), exist_ok=True)
            target = filedialog.asksaveasfilename(title="Stiahnuť obrázok ako", initialfile=name,
                                                  initialdir=self.var_dir.get(), defaultextension=ext,
                                                  filetypes=[("Obrázok", "*" + ext), ("Všetky súbory", "*.*")])
            if not target:
                return
            targets = [(p, os.path.normpath(target))]
        for src, target in targets:
            try:
                self.write(src, target)
            except (OSError, core.MarkError) as e:
                self.tree.set(src, "result", f"Chyba: {e}")
                messagebox.showerror(APP_NAME, f"{os.path.basename(src)}: {e}")
        self.set_status(f"Stiahnuté do: {self.last_dir}")

    def open_out(self):
        path = self.last_dir or self.var_dir.get()
        if not os.path.isdir(path):
            messagebox.showinfo(APP_NAME, "Priečinok zatiaľ neexistuje – najprv niečo stiahni.")
            return
        open_folder(path)

    # ------------------------------------------------------------ aktualizácia
    def check_update_quietly(self):
        try:
            num, url = updater.latest()
        except Exception:
            return
        if num > VERSION and url:
            self.root.after(0, lambda: self.btn_update.configure(text=f"Aktualizovať na verziu {num}"))

    def update_app(self):
        if not updater.is_exe():
            messagebox.showinfo(APP_NAME, "Aktualizácia funguje iba v aplikácii AI-znacka.exe.")
            return
        self.btn_update.state(["disabled"])
        self.set_status("Zisťujem, či je dostupná nová verzia…")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        ui = lambda f, *a: self.root.after(0, f, *a)
        try:
            num, url = updater.latest()
            if num <= VERSION or not url:
                ui(self._update_done, f"Máš najnovšiu verziu ({VERSION}).", None)
                return
            new = updater.download(url, lambda pct: ui(self.set_status, f"Sťahujem verziu {num}… {pct} %"))
            ui(self._update_done, None, (num, new))
        except Exception as e:
            ui(self._update_done, f"Aktualizácia sa nepodarila: {e}", None)

    def _update_done(self, message, ready):
        self.btn_update.state(["!disabled"])
        if message:
            self.set_status(message)
            messagebox.showinfo(APP_NAME, message)
            return
        num, new = ready
        if messagebox.askyesno(APP_NAME, f"Verzia {num} je stiahnutá. Reštartovať aplikáciu teraz?"):
            try:
                updater.install_and_restart(new)
            except OSError as e:
                messagebox.showerror(APP_NAME, f"Novú verziu sa nepodarilo nainštalovať: {e}")
                return
            self.root.destroy()
        else:
            os.remove(new)
            self.set_status("Aktualizácia zrušená.")

    # ------------------------------------------------------------ metadáta
    def show_meta(self, _e=None):
        sel = self.tree.focus()
        if not sel:
            return
        path = self.saved.get(sel, sel)  # po stiahnutí ukáž výsledný súbor
        try:
            with open(path, "rb") as f:
                rows, xmp = core.describe(f.read())
        except (OSError, core.MarkError) as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        win = tk.Toplevel(self.root)
        win.title(f"Metadáta – {os.path.basename(path)}")
        win.geometry("760x520")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=path, foreground="#555").pack(anchor="w")
        tv = ttk.Treeview(frm, columns=("k", "v"), show="headings", height=6)
        tv.heading("k", text="Pole")
        tv.heading("v", text="Hodnota")
        tv.column("k", width=170, stretch=False)
        tv.column("v", width=540)
        for k, v in rows:
            tv.insert("", "end", values=(k, v))
        if len(rows) == 1:
            tv.insert("", "end", values=("AI značka", "nenájdená"))
        tv.pack(fill="x", pady=8)
        ttk.Label(frm, text="Celé XMP:").pack(anchor="w")
        txt = tk.Text(frm, wrap="none", font=("Consolas", 9))
        txt.insert("1.0", xmp or "(súbor nemá XMP metadáta)")
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)


def main():
    updater.cleanup()
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:  # súbory pretiahnuté na ikonu / „Odoslať do“
        app.add(sys.argv[1:])
    root.mainloop()


if __name__ == "__main__":
    main()
