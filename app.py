import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium
from branca.element import Template, MacroElement
from streamlit_autorefresh import st_autorefresh
import os
import plotly.graph_objects as go

# --- KONFIGURASI UTAMA ---
AWSCENTER_USERNAME = "97240"
AWSCENTER_PASSWORD = "97240@2020"

BATAS_WASPADA = 1.25
BATAS_BAHAYA = 2.50  
HISTORY_FILE = "history_gelombang.csv"

PARAM_MAP = {
    'Water Level': {'url_part': 'waterlevel', 'val_col': 'wl', 'unit': 'm'},
    'Hujan': {'url_part': 'hujan', 'val_col': 'curah', 'unit': 'mm'},
    'Suhu': {'url_part': 'suhu', 'val_col': 'curah', 'unit': '°C'},
    'Kelembaban': {'url_part': 'kelembaban', 'val_col': 'curah', 'unit': '%'},
    'Kecepatan Angin': {'url_part': 'kecepatanangin', 'val_col': 'kecepatanangin', 'unit': 'm/s'},
    'Arah Angin': {'url_part': 'arahangin', 'val_col': 'arahangin', 'unit': '°'},
    'Radiasi Matahari': {'url_part': 'matahari', 'val_col': 'radiasi', 'unit': 'W/m²'},
    'Tekanan Udara': {'url_part': 'tekananudara', 'val_col': 'pp_air', 'unit': 'mbar'}
}

st.set_page_config(page_title="Peta EWS AWS Maritim", page_icon="🌊", layout="wide")

# AUTO REFRESH 5 MENIT
st_autorefresh(interval=300000, limit=None, key="maritim_refresh")

@st.cache_data(ttl=300) 
def fetch_all_data():
    session = requests.Session()
    login_url = "https://awscenter.bmkg.go.id/base/verify"
    login_data = {"username": AWSCENTER_USERNAME, "password": AWSCENTER_PASSWORD}
    
    if session.post(login_url, data=login_data).status_code != 200:
        return None, "Gagal login ke AWSCenter."

    try:
        res_map = session.get("https://awscenter.bmkg.go.id/base/marker_login_map").json()
        df_stations = pd.DataFrame(res_map)
        
        target_sites = 'Lembar|Pemenang|Kayangan'
        df_stations = df_stations[df_stations['name_station'].str.contains(target_sites, case=False, na=False)]
        df_stations = df_stations[~df_stations['name_station'].str.contains('ARG Pemenang', case=False, na=False)]
        
        df_stations['lat'] = pd.to_numeric(df_stations['lat'], errors='coerce')
        df_stations['lng'] = pd.to_numeric(df_stations['lng'], errors='coerce')
        df_stations = df_stations.dropna(subset=['lat', 'lng'])
        
        df_main = df_stations[['id_station', 'name_station', 'nama_kota', 'lat', 'lng']].copy()
        df_main['tanggal'] = df_stations.get('tanggal', 'N/A') 
    except Exception as e:
        return None, f"Gagal mengambil koordinat stasiun: {e}"

    for param_name, config in PARAM_MAP.items():
        api_url = f"https://awscenter.bmkg.go.id/dashboard/get_parameter_terkini_{config['url_part']}"
        try:
            res_param = session.get(api_url).json()
            df_param = pd.DataFrame(res_param)
            
            if not df_param.empty and config['val_col'] in df_param.columns:
                df_param[param_name] = pd.to_numeric(df_param[config['val_col']], errors='coerce')
                df_param = df_param[['id_station', param_name]]
                df_main = pd.merge(df_main, df_param, on='id_station', how='left')
            else:
                df_main[param_name] = None
        except Exception:
            df_main[param_name] = None 
            
    for param_name in PARAM_MAP.keys():
        if param_name in df_main.columns:
            df_main[param_name] = df_main[param_name].fillna(0)
        else:
            df_main[param_name] = 0

    # SISTEM HISTORY LOKAL (DATA ASLI)
    current_history = df_main[['tanggal', 'name_station', 'Water Level']].copy()
    current_history = current_history[current_history['tanggal'] != 'N/A'] 
    
    if os.path.exists(HISTORY_FILE):
        df_history = pd.read_csv(HISTORY_FILE)
        df_history = pd.concat([df_history, current_history])
        df_history = df_history.drop_duplicates(subset=['tanggal', 'name_station'])
    else:
        df_history = current_history
        
    df_history.to_csv(HISTORY_FILE, index=False)
    return df_main, None

# --- TAMPILAN DASHBOARD ---
st.title("🌊 Peta Peringatan Dini AWS Maritim")
st.markdown("Monitoring Site: **Lembar, Pemenang, Kayangan** *(Klik ikon stasiun di peta untuk melihat grafik)*")

with st.spinner('Memuat peta dan menarik data dari AWSCenter...'):
    df, error = fetch_all_data()

if error:
    st.error(error)
elif df.empty:
    st.warning("⚠️ Data stasiun untuk Lembar, Pemenang, atau Kayangan tidak ditemukan di API saat ini.")
else:
    # --- SISTEM PERINGATAN DINI (BANNER) ---
    df_bahaya = df[df['Water Level'] >= BATAS_BAHAYA]
    df_waspada = df[(df['Water Level'] >= BATAS_WASPADA) & (df['Water Level'] < BATAS_BAHAYA)]

    if not df_bahaya.empty:
        st.error(f"🚨 PERINGATAN BAHAYA: {len(df_bahaya)} stasiun mendeteksi gelombang > {BATAS_BAHAYA} meter!")
    elif not df_waspada.empty:
        st.warning(f"⚠️ PERINGATAN WASPADA: {len(df_waspada)} stasiun mendeteksi gelombang > {BATAS_WASPADA} meter.")
    else:
        st.success("✅ Kondisi tinggi gelombang di semua site terpantau AMAN.")

    # --- PEMBUATAN PETA (FOLIUM) ---
    center_lat = df['lat'].mean()
    center_lon = df['lng'].mean()
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles='OpenStreetMap')

    for idx, row in df.iterrows():
        popup_html = f"<div style='min-width: 220px; font-size: 14px;'>"
        popup_html += f"<b>{row['name_station']}</b><br>"
        popup_html += f"<span style='color: gray; font-size: 12px;'>{row['nama_kota']}</span><br>"
        popup_html += f"<span style='color: #007bff; font-size: 11px;'>🕒 Update: {row['tanggal']} UTC</span><hr style='margin: 8px 0;'>"
        
        for p_name, p_config in PARAM_MAP.items():
            val = row[p_name]
            popup_html += f"<b>{p_name}:</b> {val} {p_config['unit']}<br>"
            
        popup_html += "</div>"

        wl_val = row['Water Level']
        if wl_val >= BATAS_BAHAYA:
            pin_color = 'red'; pin_icon = 'warning-sign'
        elif wl_val >= BATAS_WASPADA:
            pin_color = 'orange'; pin_icon = 'info-sign'
        else:
            pin_color = 'green'; pin_icon = 'tint' 

        folium.Marker(
            location=[row['lat'], row['lng']],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"{row['name_station']} (Klik untuk lihat grafik)",
            icon=folium.Icon(color=pin_color, icon=pin_icon)
        ).add_to(m)

    template = """
    {% macro html(this, kwargs) %}
    <div style="position: absolute; bottom: 30px; left: 30px; width: 230px; height: 130px; background-color: white; border: 2px solid grey; z-index:9999; font-size:14px; color: black; padding: 10px; border-radius: 8px; box-shadow: 3px 3px 5px rgba(0,0,0,0.3);">
        <b style="color: black;">🌊 Keterangan Water Level</b><br>
        <hr style="margin: 5px 0; border: 1px solid grey;">
        <i class="fa fa-circle" style="color:red"></i> <span style="color: black;">Bahaya (&ge; 2.50 m)</span><br>
        <i class="fa fa-circle" style="color:orange"></i> <span style="color: black;">Waspada (1.25 - 2.49 m)</span><br>
        <i class="fa fa-circle" style="color:green"></i> <span style="color: black;">Aman (&lt; 1.25 m)</span>
    </div>
    {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(template)
    m.get_root().add_child(macro)

    # RENDER PETA DAN TANGKAP EVENT KLIK
    map_data = st_folium(m, use_container_width=True, height=650, returned_objects=["last_object_clicked"])

    # --- 📈 GRAFIK MUNCUL HANYA JIKA STASIUN DIKLIK ---
    if map_data and map_data.get("last_object_clicked"):
        clicked_lat = map_data["last_object_clicked"]["lat"]
        clicked_lng = map_data["last_object_clicked"]["lng"]
        
        df['dist'] = (df['lat'] - clicked_lat)**2 + (df['lng'] - clicked_lng)**2
        closest_idx = df['dist'].idxmin()
        
        if df.loc[closest_idx, 'dist'] < 0.001:
            selected_station = df.loc[closest_idx, 'name_station']
            
            st.markdown("---")
            st.subheader(f"📈 Grafik Gelombang: {selected_station}")
            
            if os.path.exists(HISTORY_FILE):
                df_hist = pd.read_csv(HISTORY_FILE)
                df_hist = df_hist[df_hist['name_station'] == selected_station]
                
                if not df_hist.empty:
                    # 🎯 KONVERSI WAKTU DAN RESAMPLE PER 30 MENIT (DATA ASLI)
                    df_hist['tanggal'] = pd.to_datetime(df_hist['tanggal'])
                    df_hist = df_hist.set_index('tanggal')
                    
                    # Kelompokkan data menjadi rata-rata per 30 Menit
                    df_resampled = df_hist['Water Level'].resample('30min').mean().reset_index()
                    df_resampled = df_resampled.dropna() # Buang waktu yang kosong datanya
                    
                    if not df_resampled.empty:
                        # 🎯 BIKIN GRAFIK ALA HIGHCHARTS PAKAI PLOTLY
                        fig = go.Figure()
                        
                        fig.add_trace(go.Scatter(
                            x=df_resampled['tanggal'],
                            y=df_resampled['Water Level'],
                            mode='lines+markers',
                            line=dict(color='#ff4b4b', width=3, shape='spline'), 
                            marker=dict(size=6, color='#ff4b4b', symbol='circle'),
                            fill='tozeroy', 
                            fillcolor='rgba(255, 75, 75, 0.15)', 
                            name='Tinggi Gelombang',
                            hovertemplate='<b>Waktu:</b> %{x|%d %b %Y %H:%M} UTC<br><b>Tinggi:</b> %{y:.2f} m<extra></extra>'
                        ))

                        fig.update_layout(
                            xaxis=dict(
                                rangeselector=dict(
                                    buttons=list([
                                        dict(count=24, label="24 jam", step="hour", stepmode="backward"),
                                        dict(count=3, label="3 hari", step="day", stepmode="backward"),
                                        dict(count=7, label="7 hari", step="day", stepmode="backward"),
                                        dict(step="all", label="Semua")
                                    ])
                                ),
                                rangeslider=dict(visible=True, thickness=0.08), 
                                type="date",
                                showgrid=True,
                                gridcolor='rgba(128, 128, 128, 0.2)' 
                            ),
                            yaxis=dict(
                                title="Tinggi Gelombang (Meter)",
                                showgrid=True,
                                gridcolor='rgba(128, 128, 128, 0.2)'
                            ),
                            plot_bgcolor='rgba(0,0,0,0)', 
                            paper_bgcolor='rgba(0,0,0,0)',
                            margin=dict(l=20, r=20, t=30, b=20),
                            height=400
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("🕒 Sedang mengumpulkan data per 30 menit dari server. Silakan tunggu beberapa saat lagi.")
                else:
                    st.info(f"Belum ada rekaman riwayat untuk {selected_station}.")

    # --- TABEL DATA ---
    st.markdown("---")
    st.subheader("📋 Tabel Data Terkini Stasiun Maritim")
    
    df_tabel = df.drop(columns=['lat', 'lng', 'id_station', 'dist'], errors='ignore')
    df_tabel = df_tabel.rename(columns={'name_station': 'Nama Stasiun', 'nama_kota': 'Kab/Kota', 'tanggal': 'Update Terakhir (UTC)'})
    
    cols = ['Nama Stasiun', 'Kab/Kota', 'Update Terakhir (UTC)'] + list(PARAM_MAP.keys())
    df_tabel = df_tabel[cols]

    styled_tabel = df_tabel.style.format(precision=2)
    st.dataframe(styled_tabel, use_container_width=True, hide_index=True)