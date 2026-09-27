package home.movietime.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.text.InputType;
import java.io.ByteArrayInputStream;
import java.net.URI;

/** A home-network TV shell. Telegram credentials remain on the laptop. */
public class MainActivity extends Activity {
    private WebView web;
    private SharedPreferences prefs;
    private String server;
    private View fullView;
    private WebChromeClient.CustomViewCallback fullCallback;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences("movie-time", MODE_PRIVATE);
        server = prefs.getString("server", "");
        if (server.isEmpty()) settings(""); else openLibrary();
    }

    private boolean validServer(String value) {
        try {
            URI uri = new URI(value);
            if (!"http".equals(uri.getScheme()) || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null) return false;
            if (uri.getPath()!=null && !uri.getPath().isEmpty() && !"/".equals(uri.getPath())) return false;
            String[] p=uri.getHost().split("\\.");
            if(p.length!=4) return false;
            int[] n=new int[4];for(int i=0;i<4;i++){n[i]=Integer.parseInt(p[i]);if(n[i]<0||n[i]>255)return false;}
            return n[0]==10 || (n[0]==192&&n[1]==168) || (n[0]==172&&n[1]>=16&&n[1]<=31);
        } catch(Exception e){return false;}
    }

    private void settings(String error) {
        if(web!=null){web.destroy();web=null;}
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(60,35,60,25);box.setBackgroundColor(Color.rgb(16,17,19));
        TextView title=new TextView(this);title.setText("MOVIE TIME");title.setTextSize(32);title.setTextColor(Color.rgb(234,238,144));box.addView(title);
        TextView help=new TextView(this);help.setText("Enter the laptop address shown in the Movie Time launcher.\nKeep the laptop awake and on the same Wi-Fi as this TV.");help.setTextSize(18);help.setPadding(0,15,0,15);box.addView(help);
        EditText address=new EditText(this);address.setSingleLine(true);address.setText(server);address.setHint("http://192.168.1.10:8765");address.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);box.addView(address);
        TextView warning=new TextView(this);warning.setText(error);warning.setTextColor(Color.rgb(255,160,160));box.addView(warning);
        Button connect=new Button(this);connect.setText("Connect to laptop");box.addView(connect);
        connect.setOnClickListener(v->{String value=address.getText().toString().trim();if(!value.startsWith("http://"))value="http://"+value;try{URI u=new URI(value);if(u.getPort()==-1)value="http://"+u.getHost()+":8765";}catch(Exception ignored){}if(!validServer(value)){warning.setText("Enter a local Wi-Fi address, such as http://192.168.1.10:8765");return;}server=value.replaceAll("/$", "");prefs.edit().putString("server",server).apply();openLibrary();});
        TextView tip=new TextView(this);tip.setText("Next, enter the pairing code from your laptop.\nRemote: arrows to browse, OK to select, Back to return.\nPress Menu to change the laptop address.");tip.setPadding(0,20,0,0);box.addView(tip);
        setContentView(box);address.requestFocus();
    }

    private boolean sameServer(String value){try{URI u=new URI(value),s=new URI(server);return s.getScheme().equals(u.getScheme())&&s.getHost().equals(u.getHost())&&s.getPort()==u.getPort();}catch(Exception e){return false;}}

    private void openLibrary(){
        web=new WebView(this);web.setBackgroundColor(Color.BLACK);
        web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setMediaPlaybackRequiresUserGesture(false);
        web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest r){return !sameServer(r.getUrl().toString());}
            @Override public boolean shouldOverrideUrlLoading(WebView view,String url){return !sameServer(url);}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest r){if(!sameServer(r.getUrl().toString()))return new WebResourceResponse("text/plain","utf-8",new ByteArrayInputStream(new byte[0]));return null;}
            @Override public void onPageFinished(WebView view,String url){CookieManager.getInstance().flush();}
            @Override public void onReceivedError(WebView view,WebResourceRequest r,WebResourceError e){if(r.isForMainFrame())runOnUiThread(()->settings("Cannot reach the laptop. Check its launcher, Wi-Fi, and Windows firewall."));}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public void onShowCustomView(View view,CustomViewCallback callback){fullView=view;fullCallback=callback;setContentView(view);}
            @Override public void onHideCustomView(){if(fullView!=null){fullView=null;setContentView(web);if(fullCallback!=null)fullCallback.onCustomViewHidden();fullCallback=null;}}
        });
        setContentView(web);web.loadUrl(server+"/");web.requestFocus();
    }

    @Override public boolean dispatchKeyEvent(KeyEvent e){
        if(e.getAction()==KeyEvent.ACTION_DOWN&&e.getKeyCode()==KeyEvent.KEYCODE_MENU){settings("");return true;}
        if(web!=null&&e.getAction()==KeyEvent.ACTION_DOWN){String key=null;if(e.getKeyCode()==KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)key="MediaPlayPause";if(e.getKeyCode()==KeyEvent.KEYCODE_MEDIA_REWIND)key="MediaRewind";if(e.getKeyCode()==KeyEvent.KEYCODE_MEDIA_FAST_FORWARD)key="MediaFastForward";if(key!=null){web.evaluateJavascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'"+key+"'}))",null);return true;}}
        return super.dispatchKeyEvent(e);
    }
    @Override public void onBackPressed(){
        if(fullView!=null){fullView=null;setContentView(web);if(fullCallback!=null)fullCallback.onCustomViewHidden();fullCallback=null;return;}
        if(web!=null){web.evaluateJavascript("window.movieTimeBack ? window.movieTimeBack() : false",value->{if(!"true".equals(value))new AlertDialog.Builder(this).setTitle("Movie Time").setItems(new String[]{"Keep browsing","Change laptop address","Exit"},(d,n)->{if(n==1)settings("");if(n==2)finish();}).show();});}else super.onBackPressed();
    }
    @Override protected void onPause(){super.onPause();if(web!=null){web.evaluateJavascript("document.querySelector('video') && document.querySelector('video').pause()",null);web.onPause();}CookieManager.getInstance().flush();}
    @Override protected void onResume(){super.onResume();if(web!=null)web.onResume();}
    @Override protected void onDestroy(){if(web!=null)web.destroy();super.onDestroy();}
}
