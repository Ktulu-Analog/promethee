# ============================================================================
# Prométhée — Assistant IA desktop
# ============================================================================
# Auteur  : Pierre COUGET
# Licence : GNU Affero General Public License v3.0 (AGPL-3.0)
#           https://www.gnu.org/licenses/agpl-3.0.html
# Année   : 2026
# ----------------------------------------------------------------------------
# Ce fichier fait partie du projet Prométhée.
# Vous pouvez le redistribuer et/ou le modifier selon les termes de la
# licence AGPL-3.0 publiée par la Free Software Foundation.
# ============================================================================

"""
pdf_viewer.py — Viewer PDF avec carrousel multi-pages
"""
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSlider, QFrame
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from .styles import ThemeManager


class PDFViewer(QDialog):
    """Dialogue pour prévisualiser un PDF page par page."""
    
    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.current_page = 0
        self.doc = None
        self.page_pixmaps = []
        
        self.setWindowTitle(f"Aperçu PDF - {self.pdf_path.name}")
        self.setModal(False)
        self.setMinimumSize(700, 600)
        
        self._load_pdf()
        self._setup_ui()
        self._show_page(0)
    
    def _load_pdf(self):
        """Charge le PDF et génère les aperçus de toutes les pages."""
        try:
            import fitz  # PyMuPDF
            self.doc = fitz.open(str(self.pdf_path))
            
            # Générer les aperçus de toutes les pages (résolution adaptée)
            for page_num in range(len(self.doc)):
                page = self.doc[page_num]
                
                # Résolution 150 DPI pour prévisualisation
                pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))
                img_data = pix.tobytes("png")
                
                # Convertir en QPixmap
                qimg = QImage()
                qimg.loadFromData(img_data)
                pixmap = QPixmap.fromImage(qimg)
                
                self.page_pixmaps.append(pixmap)
        
        except ImportError:
            self.page_pixmaps = []
        except Exception as e:
            print(f"[PDFViewer] Erreur chargement : {e}")
            self.page_pixmaps = []
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setObjectName("pdf_header")
        header.setStyleSheet(f"""
            QWidget#pdf_header {{
                background-color: {ThemeManager.inline('topbar_bg')};
                border-bottom: 1px solid {ThemeManager.inline('topbar_border')};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        
        # Titre
        title = QLabel(f"📄 {self.pdf_path.name}")
        title.setStyleSheet(
            f"color: {ThemeManager.inline('logo_color')}; "
            "font-size: 14px; font-weight: 600;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Info pages
        if self.page_pixmaps:
            self._page_info = QLabel(f"Page 1 / {len(self.page_pixmaps)}")
            self._page_info.setStyleSheet(
                f"color: {ThemeManager.inline('model_badge_color')}; font-size: 12px;"
            )
            header_layout.addWidget(self._page_info)
        
        layout.addWidget(header)
        
        # Zone de visualisation
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {ThemeManager.inline('pdf_viewer_bg')}; }}"
        )
        
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(
            f"background: {ThemeManager.inline('pdf_viewer_bg')}; padding: 20px;"
        )
        scroll.setWidget(self._image_label)
        
        layout.addWidget(scroll, stretch=1)
        
        # Contrôles
        if self.page_pixmaps and len(self.page_pixmaps) > 1:
            controls = QWidget()
            controls.setStyleSheet(f"""
                QWidget {{
                    background-color: {ThemeManager.inline('topbar_bg')};
                    border-top: 1px solid {ThemeManager.inline('topbar_border')};
                }}
            """)
            controls_layout = QVBoxLayout(controls)
            controls_layout.setContentsMargins(16, 12, 16, 12)
            controls_layout.setSpacing(8)
            
            # Slider
            slider_layout = QHBoxLayout()
            
            self._prev_btn = QPushButton("◄")
            self._prev_btn.setFixedSize(36, 36)
            self._prev_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeManager.inline('attachment_btn_bg')};
                    border: 1px solid {ThemeManager.inline('attachment_btn_border')};
                    border-radius: 18px;
                    color: {ThemeManager.inline('attachment_btn_color')};
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {ThemeManager.inline('attachment_btn_hover_bg')};
                }}
                QPushButton:disabled {{
                    color: {ThemeManager.inline('attachment_size_color')};
                }}
            """)
            self._prev_btn.clicked.connect(self._prev_page)
            slider_layout.addWidget(self._prev_btn)
            
            self._slider = QSlider(Qt.Orientation.Horizontal)
            self._slider.setMinimum(0)
            self._slider.setMaximum(len(self.page_pixmaps) - 1)
            self._slider.setValue(0)
            self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            self._slider.setTickInterval(1)
            self._slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    background: {ThemeManager.inline('attachment_item_border')};
                    height: 6px;
                    border-radius: 3px;
                }}
                QSlider::handle:horizontal {{
                    background: {ThemeManager.inline('attachment_btn_color')};
                    width: 16px;
                    height: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: {ThemeManager.inline('pdf_slider_hover')};
                }}
            """)
            self._slider.valueChanged.connect(self._show_page)
            slider_layout.addWidget(self._slider, stretch=1)
            
            self._next_btn = QPushButton("►")
            self._next_btn.setFixedSize(36, 36)
            self._next_btn.setStyleSheet(self._prev_btn.styleSheet())
            self._next_btn.clicked.connect(self._next_page)
            slider_layout.addWidget(self._next_btn)
            
            controls_layout.addLayout(slider_layout)
            
            # Miniatures (carrousel)
            thumbnails_scroll = QScrollArea()
            thumbnails_scroll.setWidgetResizable(False)
            thumbnails_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            thumbnails_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            thumbnails_scroll.setFixedHeight(100)
            thumbnails_scroll.setStyleSheet(f"""
                QScrollArea {{
                    border: 1px solid {ThemeManager.inline('attachment_item_border')};
                    border-radius: 6px;
                    background: {ThemeManager.inline('attachment_item_bg')};
                }}
            """)
            
            thumbs_container = QWidget()
            thumbs_layout = QHBoxLayout(thumbs_container)
            thumbs_layout.setContentsMargins(4, 4, 4, 4)
            thumbs_layout.setSpacing(6)
            
            self._thumb_labels = []
            for i, pixmap in enumerate(self.page_pixmaps):
                thumb_frame = QFrame()
                thumb_frame.setFixedSize(70, 90)
                thumb_frame.setCursor(Qt.CursorShape.PointingHandCursor)
                
                thumb_layout = QVBoxLayout(thumb_frame)
                thumb_layout.setContentsMargins(4, 4, 4, 4)
                thumb_layout.setSpacing(2)
                
                thumb_label = QLabel()
                thumb_label.setPixmap(pixmap.scaled(
                    60, 75,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_layout.addWidget(thumb_label)
                
                page_num_label = QLabel(str(i + 1))
                page_num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                page_num_label.setStyleSheet(
                    f"color: {ThemeManager.inline('attachment_size_color')}; font-size: 10px;"
                )
                thumb_layout.addWidget(page_num_label)
                
                # Style initial
                self._update_thumb_style(thumb_frame, False)
                
                # Connexion au clic
                thumb_frame.mousePressEvent = lambda e, idx=i: self._show_page(idx)
                
                thumbs_layout.addWidget(thumb_frame)
                self._thumb_labels.append(thumb_frame)
            
            thumbs_layout.addStretch()
            thumbnails_scroll.setWidget(thumbs_container)
            controls_layout.addWidget(thumbnails_scroll)
            
            layout.addWidget(controls)
        
        # Bouton fermer
        close_layout = QHBoxLayout()
        close_layout.setContentsMargins(16, 8, 16, 8)
        close_layout.addStretch()
        
        close_btn = QPushButton("Fermer")
        close_btn.setObjectName("send_btn")
        close_btn.setFixedHeight(36)
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        
        layout.addLayout(close_layout)
    
    def _update_thumb_style(self, frame: QFrame, selected: bool):
        """Met à jour le style d'une miniature."""
        if selected:
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeManager.inline('attachment_btn_hover_bg')};
                    border: 2px solid {ThemeManager.inline('attachment_btn_color')};
                    border-radius: 6px;
                }}
            """)
        else:
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: transparent;
                    border: 1px solid {ThemeManager.inline('attachment_item_border')};
                    border-radius: 6px;
                }}
                QFrame:hover {{
                    border: 2px solid {ThemeManager.inline('attachment_btn_border')};
                }}
            """)
    
    def _show_page(self, page_num: int):
        """Affiche une page spécifique."""
        if not self.page_pixmaps or page_num < 0 or page_num >= len(self.page_pixmaps):
            return
        
        self.current_page = page_num
        
        # Afficher l'image
        pixmap = self.page_pixmaps[page_num]
        self._image_label.setPixmap(pixmap)
        
        # Mettre à jour l'info
        if hasattr(self, '_page_info'):
            self._page_info.setText(f"Page {page_num + 1} / {len(self.page_pixmaps)}")
        
        # Mettre à jour le slider
        if hasattr(self, '_slider'):
            self._slider.blockSignals(True)
            self._slider.setValue(page_num)
            self._slider.blockSignals(False)
        
        # Mettre à jour les boutons
        if hasattr(self, '_prev_btn'):
            self._prev_btn.setEnabled(page_num > 0)
        if hasattr(self, '_next_btn'):
            self._next_btn.setEnabled(page_num < len(self.page_pixmaps) - 1)
        
        # Mettre à jour les miniatures
        if hasattr(self, '_thumb_labels'):
            for i, thumb in enumerate(self._thumb_labels):
                self._update_thumb_style(thumb, i == page_num)
    
    def _prev_page(self):
        """Page précédente."""
        if self.current_page > 0:
            self._show_page(self.current_page - 1)
    
    def _next_page(self):
        """Page suivante."""
        if self.current_page < len(self.page_pixmaps) - 1:
            self._show_page(self.current_page + 1)
    
    def closeEvent(self, event):
        """Nettoyage lors de la fermeture."""
        if self.doc:
            self.doc.close()
        super().closeEvent(event)
