/**
 * CookieCutterPrintService - Frontend Logic
 * Maneja upload, preview 3D con Three.js, presupuesto y pedidos.
 */

// ============================================================
// Estado global
// ============================================================
let currentJob = null;
let scene, camera, renderer, controls, stlMesh;

// ============================================================
// DOM Elements
// ============================================================
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const previewImage = document.getElementById('preview-image');
const btnGenerate = document.getElementById('btn-generate');
const paramsToggle = document.getElementById('params-toggle');
const paramsGrid = document.getElementById('params-grid');
const stepResult = document.getElementById('step-result');
const stepSuccess = document.getElementById('step-success');
const orderForm = document.getElementById('order-form');

// ============================================================
// Upload - Drag & Drop
// ============================================================
uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length) handleFile(files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    // Validar tipo
    const allowed = ['image/jpeg', 'image/jpg', 'image/png'];
    if (!allowed.includes(file.type)) {
        showToast('Formato no permitido. Usa JPG o PNG.', 'error');
        return;
    }

    // Validar tamano (10MB)
    if (file.size > 10 * 1024 * 1024) {
        showToast('Archivo demasiado grande. Max: 10 MB', 'error');
        return;
    }

    // Mostrar preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewImage.classList.remove('hidden');
        uploadZone.querySelector('.upload-content').classList.add('hidden');
    };
    reader.readAsDataURL(file);

    // Guardar referencia
    uploadZone.dataset.file = 'ready';
    btnGenerate.disabled = false;

    showToast('Imagen cargada. Haz clic en "Generar cortante".', 'info');
}

// ============================================================
// Parametros avanzados toggle
// ============================================================
paramsToggle.addEventListener('click', () => {
    paramsGrid.classList.toggle('hidden');
    paramsToggle.classList.toggle('active');
});

// ============================================================
// Generar STL y presupuesto
// ============================================================
btnGenerate.addEventListener('click', async () => {
    if (!fileInput.files.length) {
        showToast('Selecciona una imagen primero.', 'error');
        return;
    }

    setLoading(btnGenerate, true);

    try {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);

        // Parametros opcionales
        const wh = document.getElementById('wall-height').value;
        const wt = document.getElementById('wall-thickness').value;
        const hh = document.getElementById('handle-height').value;
        const ht = document.getElementById('handle-thickness').value;

        if (wh) formData.append('wall_height', wh);
        if (wt) formData.append('wall_thickness', wt);
        if (hh) formData.append('handle_height', hh);
        if (ht) formData.append('handle_thickness', ht);

        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });

        const data = await res.json();

        if (!res.ok || !data.exito) {
            throw new Error(data.detail || data.mensaje || 'Error desconocido');
        }

        currentJob = data;

        // Mostrar resultados
        displayResults(data);
        stepResult.classList.remove('hidden');
        stepResult.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Cargar preview 3D
        initThreeJS();
        loadSTL(data.job_id);

        showToast('Presupuesto generado exitosamente!', 'success');

    } catch (err) {
        console.error(err);
        showToast('Error: ' + err.message, 'error');
    } finally {
        setLoading(btnGenerate, false);
    }
});

function displayResults(data) {
    // Specs
    document.getElementById('spec-volume').textContent = data.volumen_cm3.toFixed(4) + ' cm3';
    const d = data.dimensiones_mm;
    document.getElementById('spec-dims').textContent = `${d[0].toFixed(1)} x ${d[1].toFixed(1)} x ${d[2].toFixed(1)} mm`;

    // Precio
    const p = data.precio;
    document.getElementById('price-materials').textContent = `${p.simbolo}${p.costo_materiales.toFixed(2)}`;
    document.getElementById('price-base').textContent = `${p.simbolo}${p.costo_base.toFixed(2)}`;
    document.getElementById('price-margin').textContent = `x${p.margen}`;
    document.getElementById('price-total').textContent = `${p.simbolo}${p.precio_final.toFixed(2)} ${p.moneda}`;

    // Download link
    document.getElementById('download-stl').href = data.stl_url;
}

// ============================================================
// Three.js - Visor 3D STL
// ============================================================
function initThreeJS() {
    const container = document.getElementById('threejs-container');
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    // Escena
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);

    // Luz ambiental + direccional
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(10, 20, 10);
    scene.add(dirLight);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
    dirLight2.position.set(-10, 10, -10);
    scene.add(dirLight2);

    // Camara
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(0, 0, 100);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // Controles
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 2;

    // Grid helper
    const grid = new THREE.GridHelper(100, 20, 0xcccccc, 0xe0e0e0);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -20;
    scene.add(grid);

    // Resize handler
    window.addEventListener('resize', onThreeJSResize);

    // Animacion
    animate();
}

function onThreeJSResize() {
    const container = document.getElementById('threejs-container');
    if (!container || !camera || !renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
}

function animate() {
    requestAnimationFrame(animate);
    if (controls) {
        controls.update();
    }
    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}

function loadSTL(jobId) {
    if (!scene) return;

    // Usar STLLoader
    const loader = new THREE.STLLoader();

    fetch(`/api/stl-preview/${jobId}`)
        .then(r => r.json())
        .then(data => {
            if (!data.stl_base64) {
                // Fallback: cargar directamente desde URL
                loader.load(`/api/download/${jobId}.stl`, (geometry) => {
                    displayGeometry(geometry);
                }, undefined, (err) => {
                    console.error('Error cargando STL:', err);
                    showToast('No se pudo cargar el preview 3D', 'error');
                });
                return;
            }

            // Decodificar base64
            const binary = atob(data.stl_base64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }

            const blob = new Blob([bytes], { type: 'application/octet-stream' });
            const url = URL.createObjectURL(blob);

            loader.load(url, (geometry) => {
                displayGeometry(geometry);
                URL.revokeObjectURL(url);
            }, undefined, (err) => {
                console.error('Error cargando STL:', err);
                showToast('No se pudo cargar el preview 3D', 'error');
            });
        })
        .catch(err => {
            console.error(err);
            // Intentar carga directa
            loader.load(`/api/download/${jobId}.stl`, (geometry) => {
                displayGeometry(geometry);
            });
        });
}

function displayGeometry(geometry) {
    // Material
    const material = new THREE.MeshPhongMaterial({
        color: 0xFF6B35,
        specular: 0x222222,
        shininess: 80,
        flatShading: false,
    });

    // Remover mesh anterior
    if (stlMesh) {
        scene.remove(stlMesh);
        stlMesh.geometry.dispose();
    }

    stlMesh = new THREE.Mesh(geometry, material);

    // Centrar y escalar
    geometry.computeBoundingBox();
    const center = new THREE.Vector3();
    geometry.boundingBox.getCenter(center);
    stlMesh.position.sub(center);

    // Ajustar escala para que quepa en vista
    const size = new THREE.Vector3();
    geometry.boundingBox.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    const scale = 60 / maxDim;
    stlMesh.scale.set(scale, scale, scale);

    scene.add(stlMesh);

    // Actualizar controles
    if (controls) {
        controls.reset();
        controls.autoRotate = true;
    }
}

// ============================================================
// Formulario de pedido
// ============================================================
orderForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (!currentJob) {
        showToast('Primero genera un presupuesto.', 'error');
        return;
    }

    const btn = orderForm.querySelector('button[type="submit"]');
    setLoading(btn, true);

    try {
        const formData = new FormData();
        formData.append('job_id', currentJob.job_id);
        formData.append('nombre', document.getElementById('order-name').value);
        formData.append('email', document.getElementById('order-email').value);
        formData.append('telefono', document.getElementById('order-phone').value || '');
        formData.append('notas', document.getElementById('order-notes').value || '');
        formData.append('aceptar', 'true');

        const res = await fetch('/api/order', {
            method: 'POST',
            body: formData,
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || 'Error al registrar el pedido');
        }

        // Mostrar exito
        stepResult.classList.add('hidden');
        document.getElementById('step-upload').classList.add('hidden');
        stepSuccess.classList.remove('hidden');

        // Detalles
        document.getElementById('success-details').innerHTML = `
            <p><strong>Numero de pedido:</strong> #${data.order_id}</p>
            <p><strong>Precio total:</strong> ${data.simbolo}${data.precio_final.toFixed(2)} ${data.moneda}</p>
            <p><strong>Estado:</strong> ${data.estado}</p>
        `;

        showToast(data.mensaje, 'success');

    } catch (err) {
        console.error(err);
        showToast('Error: ' + err.message, 'error');
    } finally {
        setLoading(btn, false);
    }
});

// ============================================================
// Utilidades
// ============================================================
function setLoading(btn, loading) {
    const text = btn.querySelector('.btn-text');
    const loader = btn.querySelector('.btn-loader');
    if (loading) {
        btn.disabled = true;
        text.classList.add('hidden');
        loader.classList.remove('hidden');
    } else {
        btn.disabled = false;
        text.classList.remove('hidden');
        loader.classList.add('hidden');
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // Auto-remove
    setTimeout(() => {
        if (toast.parentNode) toast.remove();
    }, 4000);
}

// ============================================================
// Inicializar
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('[CookieCutterPrintService] Frontend cargado');
});
