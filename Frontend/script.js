async function initMap() {
    const { ColorScheme } = await google.maps.importLibrary("core");

    const mapOptions = {
        center: {lat: -34.397, lng: 150.644},
        zoom: 8,
        colorScheme: ColorScheme.DARK,
    };

    const map = new google.maps.Map(
        document.getElementById("map_canvas"),
        mapOptions
    );
}