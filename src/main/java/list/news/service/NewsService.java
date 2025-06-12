package list.news.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class NewsService {

    public List<String> getNewsTitles() throws IOException {
        String url = "https://finance.naver.com/news/news_list.naver?mode=LSTD&section_id=101&section_id2=258&type=1";
        return fetchTitlesFromUrl(url);
    }

    public List<String> getInternationalNewsTitles() throws IOException {
        String INTERNATIONAL_URL = "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=403";
        return fetchTitlesFromUrl(INTERNATIONAL_URL);
    }

    public List<String> getDomesticNewsTitles() throws IOException {
        String Domestic_URL = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258";
        return fetchTitlesFromUrl(Domestic_URL);
    }

    private List<String> fetchTitlesFromUrl(String url) throws IOException {
        Document doc = Jsoup.connect(url).get();
        Elements titleElements = doc.select("dd.articleSubject > a");

        List<String> titles = new ArrayList<>();
        int count = 0;

        for (Element e : titleElements) {
            if(count >= 10) break;
            titles.add(e.text());
            count++;
        }

        return titles;
    }
}
